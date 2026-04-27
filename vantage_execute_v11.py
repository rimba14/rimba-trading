import MetaTrader5 as mt5
import os
import time
import json
import threading
import multiprocessing
import psutil
import concurrent.futures
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

# ─── Sentinel v11.0 Diagnostic Overrides ───
FORCE_TEST_TRADE = False # BYPASS SWITCH: Set to True for micro-lot test

# ─── Sentinel v11.0 Modules ───
import gitagent_sigproc as sigproc
import gitagent_hmm as hmm
import gitagent_memory as hermes_mem
import gitagent_transformer as trans
import kronos_bridge
import timesfm_bridge
import medallion_sizing as medallion
import git_arctic
import gitagent_utils as utils

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

@dataclass
class OracleSignal:
    """Native dataclass to prevent DataFrame instantiation overhead. Optimized for v11.0."""
    timestamp: float
    hmm_state: str
    kronos_prob: float
    xgboost_prob: float
    volume_percentile: float
    current_atr: float
    baseline_atr: float
    p10_boundary: float
    p90_boundary: float
    tps_base: float

@dataclass
class MemoryMatch:
    template_name: str
    cosine_similarity: float
    historical_win_rate: float

class VantageExecutor:
    """Adaptive Sentinel Execution & Risk Audit (v11.0)"""
    def __init__(self):
        self.graceful_degradation = False
        self.emergency_liquidation = False
        self.lockout_until = self._load_lockout()
        
        if not mt5.initialize():
            logging.critical("Failed to initialize MetaTrader 5.")

    def _load_lockout(self) -> float:
        if os.path.exists(CIRCUIT_LOCK_FILE := r"C:\sentinel_logs\terminal_lock.json"):
            try:
                with open(CIRCUIT_LOCK_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get("lockout_until", 0.0)
            except: pass
        return 0.0

    def _save_lockout(self, until: float):
        lock_file = r"C:\sentinel_logs\terminal_lock.json"
        os.makedirs(os.path.dirname(lock_file), exist_ok=True)
        with open(lock_file, 'w') as f:
            json.dump({"lockout_until": until, "timestamp": time.time()}, f)

    def fetch_oracle_cache(self, symbol: str) -> Optional[OracleSignal]:
        start = time.perf_counter()
        try:
            store = git_arctic.get_arctic()
            lib = store['oracle_cache']
            k_item = lib.read(f"{symbol}_kronos")
            t_item = lib.read(f"{symbol}_timesfm")
            h_item = lib.read(f"{symbol}_hmm")
            
            if (time.perf_counter() - start) > 0.1:
                logging.error(f"[{symbol}] ArcticDB Timeout (>100ms). Budget exceeded.")
                return None
                
            if not k_item or not t_item or not h_item:
                return None
                
            k_data = k_item.data.to_dict('records')[-1]
            t_data = t_item.data.to_dict('records')[-1]
            h_data = h_item.data.to_dict('records')[-1]
            
            signal = OracleSignal(
                timestamp=k_data['timestamp'],
                hmm_state=h_data['state'],
                kronos_prob=float(k_data['kronos_prob']),
                xgboost_prob=float(k_data.get('xgboost_prob', 0.50)),
                volume_percentile=float(k_data.get('vol_pct', 0.50)),
                current_atr=float(h_data.get('atr', 0.0001)),
                baseline_atr=float(k_data.get('base_atr', 0.0001)),
                p10_boundary=float(t_data['p10']),
                p90_boundary=float(t_data['p90']),
                tps_base=float(h_data.get('tps_base', 1.0))
            )
            
            if time.time() - signal.timestamp > 900:
                logging.warning(f"[{symbol}] Stale Oracle Data ({int(time.time() - signal.timestamp)}s).")
                self.graceful_degradation = True
                return None
                
            self.graceful_degradation = False
            return signal
            
        except Exception as e:
            logging.error(f"ArcticDB Sync Failure: {e}. Defaulting to Graceful Degradation.")
            self.graceful_degradation = True
            return None

    def evaluate_epistemic_gate(self, signal: OracleSignal) -> Tuple[float, bool]:
        """Returns (final_p, gate_passed)"""
        p = (signal.kronos_prob * 0.70) + (signal.xgboost_prob * 0.30)
        gate_passed = False
        
        if signal.kronos_prob > 0.65 or signal.kronos_prob < 0.35:
            consensus_passed = abs(signal.kronos_prob - signal.xgboost_prob) <= 0.30
            regime_aligned = signal.hmm_state != 'RANGE'
            sanity_passed = (signal.volume_percentile > 0.20) and (signal.current_atr < 2.5 * signal.baseline_atr)
            
            if consensus_passed and regime_aligned and sanity_passed:
                p = signal.kronos_prob
                gate_passed = True
            else:
                p = (signal.kronos_prob * 0.50) + (signal.xgboost_prob * 0.50)
                gate_passed = False
        else:
            gate_passed = True
                
        return p, gate_passed

    def calculate_sizing(self, p: float, b_ratio: float, equity: float, total_risk: float, notional: float) -> float:
        if total_risk >= 0.20 * equity:
            logging.warning(f"Portfolio Heat Cap (20%) Breach: ${total_risk:.2f} risk on ${equity:.2f} equity.")
            return 0.0
            
        if notional > 10 * equity:
            logging.warning(f"Leverage Wall (10x) Breach: ${notional:.2f} notional on ${equity:.2f} equity.")
            return 0.0
            
        q = 1.0 - p
        f_star = p - (q / b_ratio) if b_ratio > 0 else 0.0
        
        if f_star <= 0:
            logging.warning(f"TRADE BLOCKED BY KELLY: Final P is {p:.3f}, B-Ratio is {b_ratio:.2f}, resulting in negative F-star ({f_star:.4f}).")
            return 0.0
            
        return min(f_star, 0.02)

    def route_sub_orders(self, symbol: str, f_star: float, p10: float, p90: float, direction: str, atr: float, tps: float, equity: float, force_micro: bool = False):
        info = mt5.symbol_info(symbol)
        if not info: return
        
        if force_micro:
            total_volume = info.volume_min
            num_chunks = 1
            sl_val = p10 if direction == "BUY" else p90
        else:
            tick_val = info.trade_tick_value
            tick_size = info.trade_tick_size
            risk_dollars = equity * f_star
            sl_val = p10 if direction == "BUY" else p90
            sl_dist = abs(info.ask - sl_val) if direction == "BUY" else abs(info.bid - sl_val)
            total_volume = risk_dollars / (sl_dist * (tick_val / (tick_size + 1e-9)) + 1e-9)
            
            chunk_vol = round(round((total_volume / 5.0) / info.volume_step) * info.volume_step, 2)
            if chunk_vol < info.volume_min: chunk_vol = total_volume; num_chunks = 1
            else: num_chunks = 5

        comment = f"v11.0_TRACE_{'B' if direction=='BUY' else 'S'}"[:31]

        for i in range(num_chunks if not force_micro else 1):
            order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
            price = info.ask if direction == "BUY" else info.bid
            vol = float(chunk_vol if not force_micro else info.volume_min)
            
            if i > 0 and not force_micro:
                order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
                price = price - (i * 0.5 * atr) if direction == "BUY" else price + (i * 0.5 * atr)
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL if (i == 0 or force_micro) else mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": vol,
                "type": order_type,
                "price": round(float(price), info.digits),
                "sl": round(float(sl_val), info.digits),
                "tp": 0.0,
                "deviation": 20,
                "magic": 110,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC if (i == 0 or force_micro) else mt5.ORDER_FILLING_RETURN,
            }
            res = mt5.order_send(request)
            if res and res.retcode != mt5.TRADE_RETCODE_DONE:
                logging.error(f"[MT5_EXEC_FAIL] {symbol} Code: {res.retcode}, Comment: {res.comment}")
            elif res:
                logging.info(f"[MT5_EXEC_SUCCESS] {symbol} Ticket: {res.order}")

    def run_fast_loop(self, symbol: str, core_id: int):
        try:
            p = psutil.Process()
            p.cpu_affinity([core_id])
        except: pass

        memory = hermes_mem.EpisodicMemory(dim=93)
        
        while True:
            cycle_start = time.perf_counter()
            acc = mt5.account_info()
            if not acc: 
                mt5.initialize()
                time.sleep(1)
                continue

            drawdown = (acc.balance - acc.equity) / acc.balance if acc.balance > 0 else 0
            
            if FORCE_TEST_TRADE:
                logging.critical(f"[BYPASS] FORCE_TEST_TRADE enabled for {symbol}. Bypassing Phase 1-5.")
                self.route_sub_orders(symbol, 0.01, mt5.symbol_info_tick(symbol).bid*0.9, mt5.symbol_info_tick(symbol).ask*1.1, "BUY", 0.001, 1.0, acc.equity, force_micro=True)
                time.sleep(10)
                continue

            # 1. Phase 1 (Sync)
            signal = self.fetch_oracle_cache(symbol)
            stale = (self.graceful_degradation)
            
            # Check for existing positions to prevent over-trading
            existing_pos = mt5.positions_get(symbol=symbol)
            if existing_pos and len(existing_pos) > 0:
                # Cycle wait if position open
                time.sleep(1)
                continue

            # 2. Phase 3 (Memory)
            feature_vector = sigproc.get_feature_vector_native(symbol)
            mem_results = memory.retrieve(feature_vector, k=1)
            legend_active = False
            final_p = 0.50
            if mem_results and (1.0 - mem_results[0]['distance']) > 0.85:
                if 'legend_wei' in mem_results[0]['meta'].get('reasoning', ''):
                    legend_active = True
                    final_p = 0.85
            
            # 3. Phase 2 (Epistemic)
            epistemic_passed = False
            if not legend_active and signal:
                final_p, epistemic_passed = self.evaluate_epistemic_gate(signal)
                
                # REINFORCEMENT: Enforce regime alignment
                # If HMM is BEAR, but Kronos says BUY (p > 0.5), block it.
                if signal.hmm_state == 'BEAR' and final_p > 0.5:
                    epistemic_passed = False
                elif signal.hmm_state == 'BULL' and final_p < 0.5:
                    epistemic_passed = False
                elif signal.hmm_state == 'RANGE':
                    epistemic_passed = False
            
            # 4. Phase 4 (Risk Math)
            positions = mt5.positions_get()
            total_risk = sum(abs(p.profit) for p in positions) if positions else 0.0
            total_notional = sum(p.volume * p.price_open * 100 for p in positions) if positions else 0.0
            b_ratio = 1.5
            q_prob = 1.0 - final_p
            f_star_raw = final_p - (q_prob / b_ratio) if b_ratio > 0 else 0.0
            
            # --- EXECUTION AUDIT TELEMETRY ---
            print(f"\n[AUDIT][{symbol}] T:{time.strftime('%H:%M:%S')}")
            print(f"  P1 (Sync): Graceful={self.graceful_degradation}, Stale={stale}")
            print(f"  P2 (Epistemic): HMM={signal.hmm_state if signal else 'N/A'}, K_Prob={signal.kronos_prob if signal else 0:.3f}, XGB={signal.xgboost_prob if signal else 0:.3f}, Gate_Passed={epistemic_passed}, Final_P={final_p:.3f}")
            print(f"  P3 (Memory): Legend={legend_active}")
            print(f"  P4 (Risk): Heat={total_risk/acc.equity:.2%}, Notional_Mult={total_notional/acc.equity:.1f}x, B={b_ratio}, Q={q_prob:.3f}, F_Star_Raw={f_star_raw:.4f}")
            print(f"  P5 (Failsafe): Liquidation={self.emergency_liquidation}, Drawdown={drawdown:.2%}")
            
            if epistemic_passed and (final_p > 0.55 or legend_active) and not self.graceful_degradation:
                f_star = self.calculate_sizing(final_p, b_ratio, acc.equity, total_risk, total_notional)
                if f_star > 0:
                    direction = "BUY" if final_p > 0.5 else "SELL"
                    self.route_sub_orders(symbol, f_star, signal.p10_boundary, signal.p90_boundary, direction, signal.current_atr, signal.tps_base, acc.equity)

            time.sleep(max(0.1, 1.0 - (time.perf_counter() - cycle_start)))

if __name__ == "__main__":
    executor = VantageExecutor()
    watchlist = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD", "SP500", "GER40"]
    processes = []
    for i, sym in enumerate(watchlist):
        p = multiprocessing.Process(target=executor.run_fast_loop, args=(sym, i % multiprocessing.cpu_count()), daemon=True)
        p.start()
        processes.append(p)
    try:
        for p in processes: p.join()
    except KeyboardInterrupt:
        mt5.shutdown()
        sys.exit(0)
