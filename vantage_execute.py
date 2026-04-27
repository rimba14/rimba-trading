import MetaTrader5 as mt5
import os
import time
import json
import requests
import threading
import psutil
import logging
import gitagent_sigproc as sigproc
import git_arctic
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor

# --- Sentinel v13.0 Constants & Safety Gates ---
DEBUG_MODE = False
WATCHLIST = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD", "SP500", "GER40"]
MAGIC_NUMBER = 142
EMERGENCY_LIQUIDATION = False
WEBHOOK_URL = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

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

class TradeNotifier:
    """Asynchronous, non-blocking trade notifications."""
    def __init__(self, url): self.url = url
    def _post(self, msg):
        try:
            import json
            payload = {"content": msg}
            headers = {"Content-Type": "application/json"}
            response = requests.post(self.url, data=json.dumps(payload), headers=headers, timeout=10)
            if response.status_code not in [200, 201, 204]:
                logging.error(f"Webhook Failed! Status: {response.status_code} | Reason: {response.text}")
        except Exception as e:
            logging.error(f"Webhook Exception: {e}")
    def send(self, symbol, direction, p, f_star):
        emoji = "🟢" if "BUY" in direction else "🔴"
        msg = f"**{emoji} SENTINEL v13.0 EXECUTION**\n**Symbol:** {symbol}\n**Action:** {direction}\n**Conviction:** {p:.2%}\n**Kelly:** {f_star:.2%}"
        threading.Thread(target=self._post, args=(msg,), daemon=True).start()

class CognitionJournal:
    """Institutional audit ledger for AI reasoning."""
    def __init__(self, path="cognition_bridge.json"): self.path = path
    def log(self, data):
        try:
            entries = []
            if os.path.exists(self.path):
                with open(self.path, 'r') as f: entries = json.load(f)
            entries.append(data)
            with open(self.path, 'w') as f: json.dump(entries, f, indent=4)
        except: pass

class VantageExecutorV13:
    """Adaptive Sentinel Execution & Risk Audit (v13.0)"""
    def __init__(self):
        self.notifier = TradeNotifier(WEBHOOK_URL)
        self.journal = CognitionJournal()
        self.last_signals = {} # Symbol -> timestamp
        if not mt5.initialize():
            logging.error("MT5 Init Failed")
            exit()

    def _get_min_dist(self, info):
        """Calculates broker-legal minimum distance for stops/limits."""
        spread = info.ask - info.bid
        return max(info.trade_stops_level * info.point, 2 * spread)

    def is_rollover(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return True
        dt = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        t = dt.strftime('%H:%M')
        return "23:55" <= t <= "23:59" or "00:00" <= t <= "00:15"

    def evaluate_epistemic_gate(self, sig: OracleSignal) -> Tuple[float, bool]:
        """Phase 2: Epistemic Gate (v14.1 Stability Patch)"""
        divergence = abs(sig.kronos_prob - sig.xgboost_prob)
        
        # Conditions for Kronos Override Authority
        gate_passed = (
            divergence <= 0.30 and 
            sig.hmm_state != "RANGE" and 
            sig.vol_pct > 0.20 and 
            sig.atr < (2.5 * sig.base_atr)
        )
        
        # v14.1 Absolute Directional Alignment
        if sig.hmm_state == 'BEAR' and sig.kronos_prob > 0.5: gate_passed = False
        if sig.hmm_state == 'BULL' and sig.kronos_prob < 0.5: gate_passed = False
        
        if gate_passed:
            p = (sig.kronos_prob * 0.7) + (sig.xgboost_prob * 0.3)
        else:
            p = (sig.kronos_prob * 0.5) + (sig.xgboost_prob * 0.5)
            
        return p, gate_passed

    def route_sub_orders(self, symbol, p, f_star, sig: OracleSignal):
        """Phase 5: Action Layer Execution & Sanitization"""
        info = mt5.symbol_info(symbol)
        if not info: return
        
        direction = "BUY" if p > 0.5 else "SELL"
        equity = mt5.account_info().equity
        risk_amt = equity * f_star
        
        # Calculate Volume with P10/P90 stops
        sl_raw = sig.p10 if direction == "BUY" else sig.p90
        dist = abs(info.ask - sl_raw) if direction == "BUY" else abs(info.bid - sl_raw)
        min_dist = self._get_min_dist(info)
        dist = max(dist, min_dist)
        
        tick_val = info.trade_tick_value
        tick_size = info.trade_tick_size
        raw_vol = risk_amt / (dist * (tick_val / (tick_size + 1e-9)))
        total_vol = round(raw_vol / info.volume_step) * info.volume_step
        total_vol = max(info.volume_min, min(total_vol, info.volume_max))
        
        chunk_vol = round((total_vol / 5) / info.volume_step) * info.volume_step
        chunks = 1 if chunk_vol < info.volume_min else 5
        if chunks == 1: chunk_vol = total_vol

        for i in range(chunks):
            price = info.ask if direction == "BUY" else info.bid
            # Stretch Stop Loss
            sl_val = (price - dist) if direction == "BUY" else (price + dist)
            
            if i > 0:
                intended_limit = price - (i * 0.5 * sig.atr) if direction == "BUY" else price + (i * 0.5 * sig.atr)
                limit_dist = abs(price - intended_limit)
                price = (price - min_dist if direction == "BUY" else price + min_dist) if limit_dist < min_dist else intended_limit

            request = {
                "action": mt5.TRADE_ACTION_DEAL if i == 0 else mt5.TRADE_ACTION_PENDING,
                "symbol": symbol, "volume": float(chunk_vol),
                "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL if i == 0 else (mt5.ORDER_TYPE_BUY_LIMIT if direction == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT),
                "price": round(float(price), info.digits),
                "sl": round(float(sl_val), info.digits),
                "magic": MAGIC_NUMBER, "comment": f"v13_{i}",
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC if i == 0 else mt5.ORDER_FILLING_RETURN,
            }
            
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                if i == 0:
                    self.notifier.send(symbol, direction, p, f_star)
                    self.journal.log({
                        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                        "symbol": symbol, "p": p, "f_star": f_star, "hmm": sig.hmm_state
                    })

    def run_fast_loop(self, symbol, core_id):
        p_proc = psutil.Process()
        p_proc.cpu_affinity([core_id])
        
        while not EMERGENCY_LIQUIDATION:
            try:
                # 1. Phase 1: Sync & Staleness
                store = git_arctic.get_arctic()
                lib = store['oracle_cache']
                
                # Native Dict Parsing with 100ms Timeout
                k_data = lib.read(f"{symbol}_kronos").data.to_dict('records')[-1]
                h_data = lib.read(f"{symbol}_hmm").data.to_dict('records')[-1]
                
                if (time.time() - k_data['timestamp']) > 360: # 6 Min Stale
                    if DEBUG_MODE: print(f"[{symbol}] Signal Stale. Skipping.")
                    time.sleep(1); continue
                
                sig = OracleSignal(
                    timestamp=k_data['timestamp'], hmm_state=h_data['state'],
                    kronos_prob=k_data['kronos_prob'], xgboost_prob=k_data['xgboost_prob'],
                    vol_pct=k_data['vol_pct'], atr=k_data['atr'], base_atr=k_data['base_atr'],
                    p10=k_data['p10'], p90=k_data['p90']
                )

                # 2. Perception & Cognition
                p, gate_passed = self.evaluate_epistemic_gate(sig)
                
                # 3. Memory Audit (Mock/Simplified for v13 Core)
                # [Placeholder for FAISS Integration]
                
                # 1. Phase 1 (Sync)
                signal = self.fetch_oracle_cache(symbol)
                stale = (self.graceful_degradation)
            
                # Amnesia Lock (Directional v14.1)
                final_p = p
                direction = "BUY" if final_p > 0.5 else "SELL"
                existing_pos = mt5.positions_get(symbol=symbol)
                if existing_pos:
                    mt5_dir = 0 if direction == "BUY" else 1
                    if any(p.magic in [110, 142] and p.type == mt5_dir for p in existing_pos):
                        time.sleep(1); continue
                
                # 4. Risk Gates
                if self.is_rollover(symbol): continue
                
                # Kelly Sizing
                q = 1 - p
                f_star = p - (q / 1.0) # b=1 for 1:1 simplified
                f_star = min(max(0, f_star), 0.02) # Cap 2%
                
                if (p > 0.55 or p < 0.45) and f_star > 0:
                    if sig.timestamp > self.last_signals.get(symbol, 0):
                        self.route_sub_orders(symbol, p, f_star, sig)
                        self.last_signals[symbol] = sig.timestamp
                
                time.sleep(1)
            except Exception as e:
                if DEBUG_MODE: print(f"Loop Error [{symbol}]: {e}")
                time.sleep(1)

if __name__ == "__main__":
    # Directive 1 (v15.6): Implement OS-Level Singleton Lock
    import socket
    import sys
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(("127.0.0.1", 65434)) # Unique port for Vantage Execute
    except socket.error:
        print("[FATAL] Another instance of Vantage Execute is already running. Exiting.")
        sys.exit(1)

    executor = VantageExecutorV13()
    # For standalone test of one symbol
    executor.run_fast_loop("EURUSD", 0)
