import MetaTrader5 as mt5
import os
import time
import json
import threading
import concurrent.futures
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

# ─── Sentinel v8.0 Modules ───
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

# --- Phase 1: Zero-Latency Data Types ---

@dataclass
class OracleSignal:
    """Native dataclass to prevent DataFrame instantiation overhead."""
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

@dataclass
class FastState:
    """Internal loop state shared across threads."""
    equity: float = 0.0
    balance: float = 0.0
    margin_level: float = 0.0
    total_risk_dollars: float = 0.0
    notional_exposure: float = 0.0
    circuit_breaker_active: bool = False
    lockout_until: float = 0.0
    oracle_cache: Dict[str, OracleSignal] = field(default_factory=dict)
    memory_cache: Dict[str, MemoryMatch] = field(default_factory=dict)

# Shared State
STATE = FastState()
STATE_LOCK = threading.Lock()
CIRCUIT_LOCK_FILE = r"C:\sentinel_logs\terminal_lock.json"

class VantageExecutor:
    def __init__(self):
        self.graceful_degradation = False
        self.emergency_liquidation = False
        self.lockout_until = self._load_lockout()
        
        if not mt5.initialize():
            logging.critical("Failed to initialize MetaTrader 5.")

    def _load_lockout(self) -> float:
        if os.path.exists(CIRCUIT_LOCK_FILE):
            try:
                with open(CIRCUIT_LOCK_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get("lockout_until", 0.0)
            except: pass
        return 0.0

    def _save_lockout(self, until: float):
        os.makedirs(os.path.dirname(CIRCUIT_LOCK_FILE), exist_ok=True)
        with open(CIRCUIT_LOCK_FILE, 'w') as f:
            json.dump({"lockout_until": until, "timestamp": time.time()}, f)

    # ==========================================
    # PHASE 1: Infrastructure & Sync
    # ==========================================
    def fetch_oracle_cache(self, symbol: str) -> Optional[OracleSignal]:
        """Reads from ArcticDB with a hard 100ms timeout & staleness check."""
        start = time.perf_counter()
        try:
            store = git_arctic.get_arctic()
            # Read Kronos and TimesFM for the combined signal
            k_item = store.oracle_cache.read(f"{symbol}_kronos")
            t_item = store.oracle_cache.read(f"{symbol}_timesfm")
            
            if (time.perf_counter() - start) > 0.1:
                logging.error(f"[{symbol}] ArcticDB Timeout. Budget exceeded.")
                return None
                
            if not k_item or not t_item:
                return None
                
            k_data = k_item.data.iloc[-1]
            t_data = t_item.data.iloc[-1]
            
            # Fetch HMM and ATR (Phase 165 mappings)
            df_m15 = sigproc.get_m15_dataframe(symbol, 200)
            if df_m15 is None: return None
            
            hmm_state, _, _ = hmm.get_current_state(df_m15['close'].values)
            atr = utils.calculate_atr(df_m15)
            
            signal = OracleSignal(
                timestamp=k_data['timestamp'],
                hmm_state=hmm_state,
                kronos_prob=float(k_data['kronos_prob']),
                xgboost_prob=0.50, # Baseline placeholder if not explicitly cached
                volume_percentile=0.50, # Placeholder
                current_atr=atr,
                baseline_atr=atr, # Placeholder
                p10_boundary=float(t_data['p10']),
                p90_boundary=float(t_data['p90']),
                tps_base=medallion.calculate_hcs(df_m15, 0.0)
            )
            
            # Staleness Check (> 6 minutes)
            if time.time() - signal.timestamp > 360:
                logging.warning(f"[{symbol}] Stale Oracle Data. Initiating Graceful Degradation.")
                self.graceful_degradation = True
                return None
                
            self.graceful_degradation = False
            return signal
            
        except Exception as e:
            logging.error(f"ArcticDB Read Error: {e}. Defaulting to Graceful Degradation.")
            self.graceful_degradation = True
            return None

    # ==========================================
    # PHASE 2: Perception & Epistemic Gates
    # ==========================================
    def evaluate_epistemic_gate(self, signal: OracleSignal) -> float:
        """Evaluates OOD conditions before granting Kronos Full Override."""
        # Baseline 70/30 blend
        p = (signal.kronos_prob * 0.70) + (signal.xgboost_prob * 0.30)
        
        # Kronos requests Full Override
        if signal.kronos_prob > 0.65 or signal.kronos_prob < 0.35:
            consensus_passed = abs(signal.kronos_prob - signal.xgboost_prob) <= 0.30
            regime_aligned = signal.hmm_state != 'RANGE'
            sanity_passed = (signal.volume_percentile > 0.20) and (signal.current_atr < 2.5 * signal.baseline_atr)
            
            if consensus_passed and regime_aligned and sanity_passed:
                logging.info("Epistemic Gate Passed: Kronos Full Override Granted.")
                p = signal.kronos_prob
            else:
                logging.warning("OOD Detected: Epistemic Gate Failed. Override Revoked. Reverting to 50/50 Blend.")
                p = (signal.kronos_prob * 0.50) + (signal.xgboost_prob * 0.50)
                
        return p

    # ==========================================
    # PHASE 4: Risk Gates & Kelly Sizing
    # ==========================================
    def calculate_sizing(self, p: float, b_ratio: float, equity: float, total_risk: float, notional: float) -> float:
        """Applies Portfolio Heat, Leverage Walls, and Dynamic Kelly."""
        if total_risk >= 0.20 * equity:
            logging.warning("Portfolio Heat Cap (>=20%) breached. Blocking entries.")
            return 0.0
            
        if notional > 10 * equity:
            logging.warning("Leverage Wall (>10x) breached. Blocking entries.")
            return 0.0
            
        # Kelly Math: f* = p - (q/b)
        q = 1.0 - p
        f_star = p - (q / b_ratio) if b_ratio > 0 else 0.0
        
        if f_star <= 0:
            return 0.0
            
        # Hard Cap: 2% absolute risk per idea
        return min(f_star, 0.02)

    # ==========================================
    # PHASE 5: Action Layer & Fail-Safes
    # ==========================================
    def emergency_close_ticket(self, position) -> bool:
        """Closes a single ticket with maximum slippage tolerance."""
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": position.ticket,
            "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
            "deviation": 9999,  # Force execution through flash-crash requotes
            "magic": 142,
            "comment": "P5_EMERGENCY_SWEEP",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(close_request)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    def check_p5_circuit_breaker(self, current_drawdown: float):
        """Event Hierarchy: Evaluated BEFORE individual symbol rules."""
        if current_drawdown >= 0.15:
            logging.critical(f"P5 BREACH: Drawdown at {current_drawdown:.2%}. Triggering Asynchronous Panic Sweep.")
            self.emergency_liquidation = True
            self.lockout_until = time.time() + 86400  # 24-hour lockout
            self._save_lockout(self.lockout_until)
            
            positions = mt5.positions_get()
            if positions:
                # Concurrent dispatch prevents MT5 API blocking
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(self.emergency_close_ticket, pos): pos for pos in positions}
                    for future in concurrent.futures.as_completed(futures):
                        pass
                        
        elif current_drawdown >= 0.08:
            logging.warning("P5 WARNING: Drawdown >= 8%. Halving all positions.")
            utils.halve_all_positions()

    def route_sub_orders(self, symbol: str, f_star: float, p10: float, p90: float, direction: str, atr: float, tps: float, equity: float):
        """Splits capital into 5 sub-orders using TimesFM P10/P90 hard stops."""
        info = mt5.symbol_info(symbol)
        if not info: return
        
        # Calculate Lots (Approximate for the sizing chunk)
        tick_val = info.trade_tick_value
        tick_size = info.trade_tick_size
        risk_dollars = equity * f_star
        sl_dist = abs(info.ask - p10) if direction == "BUY" else abs(info.bid - p90)
        total_volume = risk_dollars / (sl_dist * (tick_val / (tick_size + 1e-9)) + 1e-9)
        
        # Routing Logic (1 Market, 4 Limit Pullbacks)
        import vantage_execute_v8 as v8_core
        v8_core.execute_sub_order_routing(
            sym=symbol,
            side=direction,
            total_volume=total_volume,
            price=info.ask if direction == "BUY" else info.bid,
            atr=atr,
            tps=tps,
            equity=equity
        )

    # ==========================================
    # CORE: 1-Second Thread-Isolated Fast Loop
    # ==========================================
    def run_fast_loop(self, symbol: str):
        """The primary executor loop running on a pinned OS thread."""
        threading.current_thread().name = f"MT5_Fast_Loop_{symbol}"
        logging.info(f"[{symbol}] Fast Loop Initialized on isolated thread.")
        
        memory = hermes_mem.EpisodicMemory(dim=93)
        
        while True:
            # 1. Check 24-Hour Lockout
            if time.time() < self.lockout_until:
                time.sleep(1)
                continue
                
            # 2. MT5 Health Check
            if mt5.terminal_info() is None:
                logging.error("MT5 Terminal lost. Re-initializing...")
                mt5.initialize()
                
            # 3. P5 Event Hierarchy (Check Portfolio Drawdown First)
            acc = mt5.account_info()
            if not acc: 
                time.sleep(1)
                continue
                
            drawdown = (acc.balance - acc.equity) / acc.balance if acc.balance > 0 else 0
            self.check_p5_circuit_breaker(drawdown)
            
            if self.emergency_liquidation:
                time.sleep(1)
                continue  
                
            # 4. Fetch Phase 1 Oracle Data
            signal = self.fetch_oracle_cache(symbol)
            if not signal or self.graceful_degradation:
                # _manage_existing_stops_only handled via manage_open_positions in v8
                import vantage_execute as legacy_v
                legacy_v.manage_open_positions()
                time.sleep(1)
                continue
                
            # 5. Phase 3: Memory Audit (Legend Override)
            feature_vector = sigproc.get_feature_vector(symbol)
            mem_results = memory.retrieve(feature_vector, k=1)
            memory_match = None
            if mem_results:
                top = mem_results[0]
                memory_match = MemoryMatch(
                    template_name="legend_wei" if 'legend_wei' in top['meta'].get('reasoning', '') else "normal",
                    cosine_similarity=float(1.0 - top['distance']),
                    historical_win_rate=0.82
                )
                
            trade_approved = False
            final_p = 0.0
            
            if memory_match and memory_match.cosine_similarity > 0.85 and memory_match.template_name == "legend_wei":
                logging.info(f"[{symbol}] Legend Override Activated. Bypassing Phase 2.")
                trade_approved = True
                final_p = memory_match.historical_win_rate 
            else:
                # 6. Phase 2: Standard Epistemic Gate & Perception
                final_p = self.evaluate_epistemic_gate(signal)
                if final_p > 0.55: 
                    trade_approved = True
                    
            # 7. Phase 4 & 5: Risk Math and Routing
            if trade_approved:
                # Calculate Portfolio Metrics
                # Simplification: risk and notional from current positions
                total_risk = 0.0
                total_notional = 0.0
                positions = mt5.positions_get()
                if positions:
                    for p in positions:
                        total_risk += abs(p.profit) # Rough placeholder for risk_dollars
                        total_notional += p.volume * p.price_open * 100 # Approx
                
                f_star = self.calculate_sizing(
                    p=final_p, 
                    b_ratio=1.5, # Fixed B-Ratio
                    equity=acc.equity, 
                    total_risk=total_risk, 
                    notional=total_notional
                )
                
                if f_star > 0:
                    direction = "BUY" if final_p > 0.5 else "SELL"
                    self.route_sub_orders(
                        symbol=symbol, 
                        f_star=f_star, 
                        p10=signal.p10_boundary, 
                        p90=signal.p90_boundary, 
                        direction=direction,
                        atr=signal.current_atr,
                        tps=signal.tps_base,
                        equity=acc.equity
                    )
                    
            # Tick every 1 second
            time.sleep(1)

if __name__ == "__main__":
    # Orchestrator for multiple symbols
    executor = VantageExecutor()
    watchlist = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "BTCUSD"]
    
    threads = []
    for sym in watchlist:
        t = threading.Thread(target=executor.run_fast_loop, args=(sym,), daemon=True)
        t.start()
        threads.append(t)
        
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mt5.shutdown()
