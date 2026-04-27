import MetaTrader5 as mt5
import os
import time
import json
import requests
import threading
import psutil
import logging
import sys
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor

# --- Sentinel v13.0 Modules ---
import gitagent_sigproc as sigproc
import gitagent_memory as hermes_mem
import git_arctic
import gitagent_utils as utils

# --- Sentinel v13.0 Constants & Safety Gates ---
DEBUG_MODE = False
from sentinel_config import WATCHLIST
MAGIC_NUMBER = 142
EMERGENCY_LIQUIDATION = False
MAX_HEAT_CAP = 0.20        # 20% Total Portfolio Heat
MAX_HARD_RISK = 0.02       # 2% Per Idea
MAX_LEVERAGE = 10.0        # 10x Max Notional
PANIC_DRAWDOWN = 0.15      # 15% Max Equity Drawdown
ORACLE_STALENESS = 360     # 6 Minutes (Slow Loop Sync)

@dataclass
class OracleSignal:
    timestamp: float
    hmm_state: str
    kronos_prob: float
    xgboost_prob: float
    vol_pct: float
    atr: float
    base_atr: float
    p10: float
    p90: float
    tps_base: float = 1.0

class CognitionJournal:
    """Institutional audit ledger for AI reasoning."""
    def __init__(self, path="C:\\Sentinel_Project\\cognition_bridge.json"): self.path = path
    def log(self, data):
        try:
            entries = []
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f: entries = json.load(f)
            entries.append(data)
            with open(self.path, 'w', encoding='utf-8') as f: json.dump(entries[-1000:], f, indent=4)
        except Exception as e:
            if DEBUG_MODE: print(f"[JOURNAL_ERR] {e}")

class VantageExecutorV13:
    """Adaptive Sentinel Execution & Risk Audit (v13.0)"""
    def __init__(self):
        self.journal = CognitionJournal()
        self.last_signal_ts = {}
        
        # Setup File Logging for Fast Loop
        self.logger = logging.getLogger("v13_executor")
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            fh = logging.FileHandler('C:\\sentinel_logs\\fast_loop_v13.log')
            fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
            self.logger.addHandler(fh)
        
        if not mt5.initialize():
            self.logger.error("MT5 Initialization Failed")
            sys.exit(1)

    def _get_min_dist(self, symbol_info):
        """Calculates broker-legal minimum distance for stops/limits."""
        spread = symbol_info.ask - symbol_info.bid
        floor = max(symbol_info.trade_stops_level * symbol_info.point, 2 * spread)
        return floor

    def is_rollover(self, symbol):
        """Block entries during liquidity vacuum (23:55-00:15)."""
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return True
        dt = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        t = dt.strftime('%H:%M')
        return "23:55" <= t <= "23:59" or "00:00" <= t <= "00:15"

    def evaluate_epistemic_gate(self, sig: OracleSignal) -> Tuple[float, bool]:
        """Phase 2: Epistemic Gate (OOD Defense)"""
        divergence = abs(sig.kronos_prob - sig.xgboost_prob)
        
        # 1. Gate Conditions
        gate_passed = (
            divergence <= 0.30 and 
            sig.hmm_state != "RANGE" and 
            sig.vol_pct > 0.20 and 
            sig.atr < (2.5 * sig.base_atr)
        )
        
        # 2. Blending Logic
        if gate_passed:
            # Kronos Override (70/30)
            p = (sig.kronos_prob * 0.7) + (sig.xgboost_prob * 0.3)
        else:
            # Defensive (50/50)
            p = (sig.kronos_prob * 0.5) + (sig.xgboost_prob * 0.5)
            
        return p, gate_passed

    def panic_sweep(self):
        """P5 Circuit Breaker: Concurrent liquidation of all orders."""
        global EMERGENCY_LIQUIDATION
        print("\n" + "!"*50 + "\nCRITICAL: P5 PANIC SWEEP TRIGGERED\n" + "!"*50)
        EMERGENCY_LIQUIDATION = True
        
        positions = mt5.positions_get()
        orders = mt5.orders_get()
        
        def close_pos(p):
            tick = mt5.symbol_info_tick(p.symbol)
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "price": tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask,
                "deviation": 9999,
                "magic": MAGIC_NUMBER,
                "comment": "P5_PANIC"
            }
            return mt5.order_send(request)

        def cancel_order(o):
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": o.ticket
            }
            return mt5.order_send(request)

        with ThreadPoolExecutor(max_workers=10) as executor:
            if positions: executor.map(close_pos, positions)
            if orders: executor.map(cancel_order, orders)
            
        print("[SUCCESS] Global Liquidation Complete.", flush=True)
        sys.exit(0)

    def route_sub_orders(self, symbol, p, f_star, sig: OracleSignal):
        """Phase 5: Sub-Order Routing & Sanitization"""
        info = mt5.symbol_info(symbol)
        if not info: return
        
        direction = "BUY" if p > 0.5 else "SELL"
        acc = mt5.account_info()
        risk_dollars = acc.equity * f_star
        
        # 1. Stop Loss Boundaries (TimesFM P10/P90)
        sl_raw = sig.p10 if direction == "BUY" else sig.p90
        
        # 2. Stretch Logic (Min distance floor)
        min_dist = self._get_min_dist(info)
        price_ref = info.ask if direction == "BUY" else info.bid
        
        actual_sl_dist = abs(price_ref - sl_raw)
        if actual_sl_dist < min_dist:
            sl_val = (price_ref - min_dist) if direction == "BUY" else (price_ref + min_dist)
        else:
            sl_val = sl_raw
            
        # 3. Size Calculation
        tick_val = info.trade_tick_value
        tick_size = info.trade_tick_size
        sl_dist_points = abs(price_ref - sl_val) / (info.point + 1e-12)
        
        # Total Volume = (Risk $ / (Points * Point Value))
        # Point Value = Tick Value / (Tick Size / Point)
        point_val = tick_val / (tick_size / info.point)
        total_vol = risk_dollars / (sl_dist_points * point_val + 1e-12)
        total_vol = round(total_vol / info.volume_step) * info.volume_step
        total_vol = max(info.volume_min, min(total_vol, info.volume_max))
        
        # 4. Split into 5 chunks (1 Market, 4 Limits)
        chunk_vol = round((total_vol / 5) / info.volume_step) * info.volume_step
        chunks = 5 if chunk_vol >= info.volume_min else 1
        if chunks == 1: chunk_vol = total_vol

        for i in range(chunks):
            current_price = info.ask if direction == "BUY" else info.bid
            
            if i == 0:
                order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
                entry_price = current_price
                action = mt5.TRADE_ACTION_DEAL
            else:
                order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
                # Pullback at 0.5x ATR per level
                pullback = i * 0.5 * sig.atr
                entry_price = (current_price - pullback) if direction == "BUY" else (current_price + pullback)
                action = mt5.TRADE_ACTION_PENDING
                
                # Stretch limit if too close to market
                if abs(current_price - entry_price) < min_dist:
                    entry_price = (current_price - min_dist) if direction == "BUY" else (current_price + min_dist)

            request = {
                "action": action,
                "symbol": symbol,
                "volume": float(chunk_vol),
                "type": order_type,
                "price": round(float(entry_price), info.digits),
                "sl": round(float(sl_val), info.digits),
                "tp": 0.0,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": f"v13_{i}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC if i == 0 else mt5.ORDER_FILLING_RETURN,
            }
            
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                if DEBUG_MODE: print(f"[SUCCESS] {symbol} Chunk {i} placed at {entry_price}")
            else:
                if DEBUG_MODE: print(f"[FAIL] {symbol} Chunk {i}: {res.comment if res else 'No Response'}")

        # Final Log
        self.journal.log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol, "direction": direction, "p": p, "f_star": f_star,
            "hmm": sig.hmm_state, "sl": sl_val
        })

    def run_fast_loop(self, symbol, core_id):
        """Main Institutional Fast Loop Execution."""
        # CPU Pinning
        try:
            p_proc = psutil.Process()
            p_proc.cpu_affinity([core_id])
        except: pass
        
        # Local Infrastructure Init
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        memory = hermes_mem.EpisodicMemory(dim=93)
        
        if DEBUG_MODE: self.logger.info(f"[SYNC] Fast Loop started for {symbol} on CPU {core_id}")
        
        while not EMERGENCY_LIQUIDATION:
            cycle_start = time.perf_counter()
            try:
                # --- PHASE 1: Sync & Staleness ---
                t_read_start = time.perf_counter()
                k_item = lib.read(f"{symbol}_kronos")
                h_item = lib.read(f"{symbol}_hmm")
                t_item = lib.read(f"{symbol}_timesfm")
                t_read_dur = time.perf_counter() - t_read_start
                
                if t_read_dur > 0.1 and DEBUG_MODE:
                    print(f"[WARN] ArcticDB Latency: {t_read_dur:.3f}s for {symbol}")
                
                # Zero-Latency Dataclass Parsing (Native Dicts)
                if k_item.data.empty or h_item.data.empty or t_item.data.empty:
                    if DEBUG_MODE: self.logger.warning(f"[DATA_MISSING] {symbol} lacks required oracle cache. Skipping.")
                    time.sleep(1); continue
                    
                k_data = k_item.data.to_dict('records')[-1]
                h_data = h_item.data.to_dict('records')[-1]
                t_data = t_item.data.to_dict('records')[-1]
                
                # Staleness Check (6 mins)
                # We check both Kronos and TimesFM for sync integrity
                max_age = max(time.time() - k_data['timestamp'], time.time() - t_data['timestamp'])
                if max_age > ORACLE_STALENESS:
                    if DEBUG_MODE: self.logger.info(f"[STALE] {symbol} Signal too old ({max_age:.0f}s). Entering Graceful Degradation.")
                    time.sleep(1); continue
                
                sig = OracleSignal(
                    timestamp=k_data['timestamp'], hmm_state=h_data['state'],
                    kronos_prob=k_data['kronos_prob'], xgboost_prob=k_data['xgboost_prob'],
                    vol_pct=k_data['vol_pct'], atr=h_data['atr'], base_atr=k_data['base_atr'],
                    p10=t_data['p10'], p90=t_data['p90']
                )

                # --- PHASE 2: Epistemic Gates ---
                p, gate_passed = self.evaluate_epistemic_gate(sig)
                
                # --- PHASE 3: Memory Audit ---
                feature_vector = sigproc.get_feature_vector_native(symbol)
                mem_results = memory.retrieve(feature_vector, k=1)
                
                legend_match = False
                if mem_results and (1.0 / (1.0 + mem_results[0]['distance'])) > 0.85:
                    reasoning = mem_results[0]['meta'].get('reasoning', '').lower()
                    if 'legend_wei' in reasoning:
                        p = mem_results[0]['meta'].get('win_rate', p)
                        legend_match = True
                        if DEBUG_MODE: print(f"[LEGEND] {symbol} Short-Circuit Active! Sim: {1.0/(1.0+mem_results[0]['distance']):.2f}")

                # --- PHASE 4: Risk Gates & Sizing ---
                acc = mt5.account_info()
                if not acc: continue
                
                # P5 Circuit Breaker
                drawdown = (acc.balance - acc.equity) / acc.balance if acc.balance > 0 else 0
                if drawdown >= PANIC_DRAWDOWN:
                    self.panic_sweep()
                
                # Amnesia Lock (magic=142): Check for same-direction overlap
                direction = "BUY" if p > 0.5 else "SELL"
                existing = mt5.positions_get(symbol=symbol, magic=MAGIC_NUMBER)
                if existing:
                    # MT5 Type: 0 = Buy, 1 = Sell
                    mt5_dir = 0 if direction == "BUY" else 1
                    if any(pos.type == mt5_dir for pos in existing):
                        if DEBUG_MODE: print(f"[AMNESIA] {symbol} {direction} position already exists. Skipping.")
                        time.sleep(1); continue
                
                # Rollover Blackout
                if self.is_rollover(symbol):
                    time.sleep(1); continue
                
                # Kelly Criterion (f* = p - (q/b))
                # Normalize p for directional success probability
                p_directional = p if p > 0.5 else (1.0 - p)
                b_ratio = 1.5
                q_prob = 1.0 - p_directional
                f_star = p_directional - (q_prob / b_ratio) if b_ratio > 0 else 0.0
                
                # Risk Caps
                f_star = min(f_star, MAX_HARD_RISK)
                
                # Portfolio Heat Check (20%)
                total_risk = sum(abs(pos.profit) for pos in mt5.positions_get())
                if (total_risk / acc.equity) >= MAX_HEAT_CAP:
                    if DEBUG_MODE: print(f"[HEAT] {symbol} Blocked: {total_risk/acc.equity:.2%} cap reached")
                    time.sleep(1); continue
                
                # Leverage Wall (10x)
                total_notional = sum(pos.volume * pos.price_open * 100 for pos in mt5.positions_get())
                if (total_notional / acc.equity) >= MAX_LEVERAGE:
                    if DEBUG_MODE: print(f"[LEVERAGE] {symbol} Blocked: {total_notional/acc.equity:.1f}x wall reached")
                    time.sleep(1); continue

                # --- PHASE 5: Action Layer ---
                if (p > 0.55 or p < 0.45 or legend_match) and f_star > 0:
                    # Sync gate: Check if signal is actually new
                    if sig.timestamp > self.last_signal_ts.get(symbol, 0):
                for symbol in symbols:
                    # 1. Phase 1: Sync & Staleness
                    store = git_arctic.get_arctic()
                    lib = store['oracle_cache']
                    
                    try:
                        k_item = lib.read(f"{symbol}_kronos")
                        h_item = lib.read(f"{symbol}_hmm")
                        
                        if k_item.data.empty or h_item.data.empty:
                            continue
                            
                        k_data = k_item.data.to_dict('records')[-1]
                        h_data = h_item.data.to_dict('records')[-1]
                    except:
                        continue
                    
                    # Staleness check
                    max_age = time.time() - k_data['timestamp']
                    if max_age > 360: # 6 Min Stale
                        if DEBUG_MODE: logging.info(f"[STALE] {symbol} Signal too old ({max_age:.0f}s). Skipping.")
                        continue
                    
                    sig = OracleSignal(
                        timestamp=k_data['timestamp'], hmm_state=h_data['state'],
                        kronos_prob=k_data['kronos_prob'], xgboost_prob=k_data['xgboost_prob'],
                        vol_pct=k_data['vol_pct'], atr=k_data['base_atr'], base_atr=k_data['base_atr'],
                        p10=k_data.get('p10', 0), p90=k_data.get('p90', 0)
                    )

                    # 2. Perception & Cognition
                    p, gate_passed = self.evaluate_epistemic_gate(sig)
                    
                    # 3. Amnesia Lock
                    final_p = p
                    direction = "BUY" if final_p > 0.5 else "SELL"
                    existing_pos = mt5.positions_get(symbol=symbol)
                    if existing_pos:
                        mt5_dir = 0 if direction == "BUY" else 1
                        if any(p.magic in [110, 142] and p.type == mt5_dir for p in existing_pos):
                            continue
                    
                    # 4. Risk Gates
                    if self.is_rollover(symbol): continue
                    
                    # Kelly Sizing
                    p_directional = p if p > 0.5 else (1.0 - p)
                    q_prob = 1.0 - p_directional
                    f_star = p_directional - (q_prob / 1.5)
                    f_star = min(max(0, f_star), MAX_HARD_RISK)
                    
                    # Audit Log
                    acc = mt5.account_info()
                    heat = (acc.balance - acc.equity) / acc.balance if acc.balance > 0 else 0
                    logging.info(f"[AUDIT][{symbol}] T:{datetime.now().strftime('%H:%M:%S')} | P={p:.3f} | Heat={heat:.2%} | DD={-heat:.2%}")

                    if (p > 0.55 or p < 0.45) and f_star > 0:
                        if sig.timestamp > self.last_signals.get(symbol, 0):
                            self.route_sub_orders(symbol, p, f_star, sig)
                            self.last_signals[symbol] = sig.timestamp
                
                # Dynamic sleep to maintain 1s cycle for the WHOLE list
                elapsed = time.time() - loop_start
                time.sleep(max(0.1, 1.0 - elapsed))
                
            except Exception as e:
                logging.error(f"Global Loop Error: {e}")
                time.sleep(1)
            
            # Precision Sleep to hit 1s tick
            elapsed = time.perf_counter() - cycle_start
            time.sleep(max(0.01, 1.0 - elapsed))

def _mp_entry(symbol, core_id):
    executor = VantageExecutorV13()
    executor.run_fast_loop(symbol, core_id)

if __name__ == "__main__":
    import multiprocessing
    processes = []
    for i, symbol in enumerate(WATCHLIST):
        p = multiprocessing.Process(target=_mp_entry, args=(symbol, i % multiprocessing.cpu_count()), daemon=True)
        p.start()
        processes.append(p)
        
    try:
        for p in processes: p.join()
    except KeyboardInterrupt:
        mt5.shutdown()
        sys.exit(0)
