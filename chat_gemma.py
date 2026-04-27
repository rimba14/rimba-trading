import MetaTrader5 as mt5
import os
import time
import json
import threading
import psutil
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import concurrent.futures

# --- Adaptive Sentinel v16.9 Production Build ---
# System Command: Adaptive Sentinel Execution & Risk Audit
DEBUG_MODEL_ID = "qwen2.5-coder:3b" # Mixture-of-Experts logic (v16.9)
DEBUG_MODE = True  
from sentinel_config import WATCHLIST, BROKER_SUFFIX, KELLY_FRACTION
ARCTIC_URI = "lmdb://c:/sentinel_arctic"
LOCKOUT_FILE = r"C:\sentinel_logs\terminal_lock.json"
EMERGENCY_LIQUIDATION = False
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"
MAGIC_NUMBER = 142
GLOBAL_TEMPERATURE = 3.0 # Final-stage signal expansion

# --- Heartbeat Dashboard State ---
heartbeat_state = {}
heartbeat_lock = threading.Lock()

import gitagent_sigproc as sigproc
import gitagent_hmm as hmm
import gitagent_memory as hermes_mem
import gitagent_bars as bars
import git_arctic
import gitagent_utils as utils
# Configure Logging
log_file = r"C:\sentinel_logs\fast_loop_v16_9.log"
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [FAST_LOOP] %(message)s',
    force=True,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)
print("[TRACE] All Sentinel modules imported")

# Directive: Fast Loop Singleton Pattern (v16.9)
from arcticdb import Arctic
institutional_ledger = Arctic('lmdb://./data/arctic_cache')
lib_cache = institutional_ledger['oracle_cache'] if 'oracle_cache' in institutional_ledger.list_libraries() else institutional_ledger.create_library('oracle_cache')

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
    primary_dir: int # 1, -1, 0
    meta_conviction: float # p(correct)

@dataclass
class ExecutionAudit:
    symbol: str
    p1_sync: bool = False
    p2_gate: bool = False
    p3_memory: bool = False
    p4_risk: bool = False
    final_p: float = 0.5
    f_star: float = 0.0
    reasoning: str = ""
    is_legend: bool = False


class TradeNotifier:
    """Asynchronous, non-blocking trade notifications via Webhooks."""
    def __init__(self, webhook_url=""):
        self.webhook_url = webhook_url

    def _send_http_post(self, payload: Dict[str, Any]):
        if not self.webhook_url: return
        try:
            import requests
            import json
            headers = {"Content-Type": "application/json"}
            response = requests.post(self.webhook_url, data=json.dumps(payload), headers=headers, timeout=10)
            if response.status_code not in [200, 201, 204]:
                logging.error(f"Webhook Failed! Status: {response.status_code} | Reason: {response.text}")
        except Exception as e:
            logging.error(f"Webhook Exception: {e}")

    def send_alert(self, symbol: str, direction: str, final_p: float, f_star: float):
        emoji = "🟢" if direction == "BUY" else "🔴"
        timestamp = datetime.now().strftime('%H:%M:%S')
        msg = (
            f"**{emoji} ADAPTIVE SENTINEL EXECUTION (v12.0)**\n"
            f"**Symbol:** {symbol}\n"
            f"**Action:** {direction}\n"
            f"**Conviction:** {final_p:.2%}\n"
            f"**Size (Kelly):** {f_star:.2%}\n"
            f"**Time:** {timestamp} UTC\n"
            f"🧠 *Reasoning captured in Cognition Ledger.*"
        )
        payload = {"content": msg}
        import threading
        threading.Thread(target=self._send_http_post, args=(payload,), daemon=True).start()

class SentinelV15:
    def __init__(self):
        self.lockout_until = self._load_lockout()
        self.last_signals: Dict[str, float] = {} # Track signal timestamps per symbol
        self.notifier = TradeNotifier(webhook_url=DISCORD_WEBHOOK)
        self.memory_auditor = None # Initialize inside the process
        
        # Directive 1: Setup the Queue Directory
        self.signal_queue_dir = "pending_signals"
        os.makedirs(self.signal_queue_dir, exist_ok=True)
        
        # Setup Logger
        self.logger = logging.getLogger("sentinel_v15")
        self.logger.setLevel(logging.INFO)

        self.memory_auditor = None
        
    def _load_lockout(self) -> float:
        if os.path.exists(LOCKOUT_FILE):
            try:
                with open(LOCKOUT_FILE, 'r') as f:
                    return json.load(f).get("lockout_until", 0.0)
            except: pass
        return 0.0

    def _save_lockout(self, duration_hours: int = 24):
        until = time.time() + (duration_hours * 3600)
        os.makedirs(os.path.dirname(LOCKOUT_FILE), exist_ok=True)
        with open(LOCKOUT_FILE, 'w') as f:
            json.dump({"lockout_until": until, "timestamp": time.time()}, f)
        return until

    def watchdog_check(self, symbol: str):
        """MT5 Connection Watchdog (Phase 5) with retry logic."""
        if mt5.terminal_info() is None:
            self.logger.warning(f"[{symbol}] MT5 Connection lost. Re-initializing...")
            for attempt in range(5):
                # Add jitter to prevent mass-collision
                time.sleep(0.1 * (attempt + 1) * (1 + 0.5 * (hash(symbol) % 10) / 10.0))
                if mt5.initialize():
                    self.logger.info(f"[{symbol}] MT5 Initialized successfully on attempt {attempt+1}.")
                    return True
            return False
        return True
 
    def fetch_arctic_data(self, symbol: str) -> Optional[OracleSignal]:
        """Phase 1: Zero-Latency Data Retrieval (Universal Resolver)"""
        try:
            # Reusing Global Singleton lib_cache
            
            # Directive: Universal Symbol Resolver (Strip broker suffixes)
            base_sym = symbol.split('.')[0].split('-')[0].split('+')[0].split('_')[0]
            
            # Phase 1: Universal UTC & 5.0s Timeout Gate
            with ThreadPoolExecutor(max_workers=1) as executor:
                try:
                    f_k = executor.submit(lib_cache.read, f"{base_sym}_kronos")
                    f_t = executor.submit(lib_cache.read, f"{base_sym}_timesfm")
                    f_h = executor.submit(lib_cache.read, f"{base_sym}_hmm")
                    f_m = executor.submit(lib_cache.read, f"{base_sym}_meta")
                    
                    k_item = f_k.result(timeout=0.3)
                    t_item = f_t.result(timeout=0.3)
                    h_item = f_h.result(timeout=0.3)
                    m_item = f_m.result(timeout=0.3)
                except TimeoutError:
                    self.logger.warning(f"[TIMEOUT] ArcticDB Read > 300ms for {symbol}")
                    with heartbeat_lock: heartbeat_state[symbol] = "Phase 1: ARCTIC_TIMEOUT"
                    return None
                except Exception as e:
                    self.logger.warning(f"ArcticDB Read Error for {base_sym}: {e}")
                    return None
            
            # Zero-Latency Parsing
            k_vals = k_item.data.to_dict('list')
            t_vals = t_item.data.to_dict('list')
            h_vals = h_item.data.to_dict('list')
            m_vals = m_item.data.to_dict('list')

            # Directive 2: Maintain the 360s Staleness Hard-Cap (v16.9)
            signal_ts = float(k_vals['timestamp'][-1])
            staleness = utils.get_utc_epoch() - signal_ts
            if staleness > 360:
                self.logger.warning(f"[STALE_SIGNAL] {symbol} is {staleness:.1f}s old. HALTING ENTRY.")
                with heartbeat_lock: heartbeat_state[symbol] = "Phase 1: STALE_SIGNAL"
                return None
            
            signal = OracleSignal(
                timestamp=signal_ts,
                hmm_state=str(h_vals['state'][-1]),
                kronos_prob=float(k_vals['kronos_prob'][-1]),
                xgboost_prob=float(k_vals.get('xgboost_prob', [0.5])[-1]),
                vol_pct=float(k_vals.get('vol_pct', [0.5])[-1]),
                atr=float(h_vals.get('atr', [0.0001])[-1]),
                base_atr=float(k_vals.get('base_atr', [0.0001])[-1]),
                p10=float(t_vals['p10'][-1]),
                p90=float(t_vals['p90'][-1]),
                primary_dir=int(m_vals.get('primary_dir', [0])[-1]),
                meta_conviction=float(m_vals.get('meta_conviction', [0.5])[-1])
            )
            
            return signal
        except Exception as e:
            self.logger.error(f"fetch_arctic_data critical error for {symbol}: {e}")
            return None

    def evaluate_epistemic_gate(self, symbol: str, sig: OracleSignal) -> Tuple[float, bool, str]:
        """Phase 2: The Epistemic Gate (0.82 Threshold & Regime Filter)"""
        # 1. Base Epistemic Blending
        p_final = sig.meta_conviction
        direction = "BUY" if sig.primary_dir == 1 else ("SELL" if sig.primary_dir == -1 else "HOLD")
        
        # 2. Strict Regime Alignment (Directive 2)
        alignment_ok = True
        if sig.hmm_state == 'BEAR' and direction == "BUY": alignment_ok = False
        if sig.hmm_state == 'BULL' and direction == "SELL": alignment_ok = False
        if direction == "HOLD": alignment_ok = False

        # 3. 0.82 Epistemic Gate (Directive: v16.9 Production)
        gate_passed = alignment_ok and (sig.meta_conviction >= 0.82)
        
        # 4. Global Regime Filter (Block Volatile or Low Volume)
        regime_ok = (sig.hmm_state != 'VOLATILE')
        sanity_ok = (sig.vol_pct > 0.20) and (sig.atr < 2.5 * sig.base_atr)
        
        gate_passed = gate_passed and regime_ok and sanity_ok
        
        if gate_passed:
            reason = f"SUCCESS (Meta-Labeling p={sig.meta_conviction:.3f})"
        else:
            p_final = 0.50
            reason = f"REJECTED: Meta_P={sig.meta_conviction:.3f}, Align={alignment_ok}, HMM={sig.hmm_state}"
        
        return p_final, gate_passed, reason

    def check_graveyard(self, symbol: str, sig: OracleSignal) -> Tuple[bool, str]:
        """Phase 3 (The Graveyard): Similarity check against past failures."""
        try:
            import gitagent_memory as hermes_mem
            import gitagent_sigproc as sigproc
            mem = hermes_mem.EpisodicMemory(dim=93)
            
            # Construct current 93-dim vector
            vec = sigproc.get_feature_vector_native(symbol)
            # Inject context bits
            hmm_map = {"BULL": 0, "BEAR": 1, "RANGE": 2, "VOLATILE": 3}
            vec[60] = hmm_map.get(sig.hmm_state, 2)
            vec[61] = float(sig.kronos_prob)
            vec[62] = float(sig.vol_pct)
            
            regime = utils.get_symbol_regime(symbol)
            regime_map = {"FOREX_USD": 0, "FOREX_CROSS": 1, "INDEX": 2, "COMMODITY": 3, "CRYPTO": 4, "EQUITY": 5}
            vec[63] = regime_map.get(regime, 6)
            
            # Retrieve similar past failures
            results = mem.retrieve(vec, k=5)
            for res in results:
                # FAISS IndexFlatL2 returns squared Euclidean distance. 
                # Threshold of 85% similarity (approx 0.15 distance if normalized)
                if res['meta'].get('lesson') == "post_mortem_failure":
                    # Check similarity (Inner Product) > 0.85
                    if res['distance'] > 0.85: 
                        return True, f"[BLOCKED: GRAVEYARD SIMILARITY] (Sim: {res['distance']:.2%})"
        except Exception as e:
            self.logger.error(f"Graveyard check error: {e}")
            
        return False, ""

    def memory_audit(self, symbol: str) -> Tuple[float, bool]:
        """Phase 3: Contextual Memory Audit (Legend Override)"""
        if not self.memory_auditor: return 0.5, False
        
        feature_vector = sigproc.get_feature_vector_native(symbol)
        is_legend, similarity = self.memory_auditor.check_legend_override(feature_vector)
        
        if is_legend and similarity > 0.85:
            # Phase 3: Legend Override
            # Bypass all Phase 2 HMM penalties and grant execution clearance.
            # Overwrite p with matched template's historical win-rate (default 0.88 for legends)
            if DEBUG_MODE: print(f"[P3][{symbol}] Legend Match Found (Sim:{similarity:.2%}). Overriding Phase 2.")
            return 0.88, True 
                
        return 0.5, False


    def route_orders(self, symbol: str, f_star: float, p: float, sig: OracleSignal):
        """Phase 5: Signal Dispatcher (The Radar)"""
        # Package the Signal Payload (Simplified for Phase 5 MCP)
        timestamp = int(time.time())
        
        payload = {
            "symbol": symbol,
            "kronos_conviction": round(float(p), 4),
            "hmm_state": sig.hmm_state,
            "timestamp": timestamp
        }
        
        # 3. Write to Directory-Based Queue (Avoid Race Conditions)
        filename = os.path.join(self.signal_queue_dir, f"{symbol}_{timestamp}.json")
        try:
            with open(filename, 'w') as f:
                json.dump(payload, f, indent=4)
            print(f"\033[1m[RADAR] High-Conviction Signal detected. Written to {filename}\033[0m")
        except Exception as e:
            self.logger.error(f"Failed to hand off signal for {symbol}: {e}")

    def log_cognition(self, symbol: str, direction: str, p: float, f_star: float, sig: OracleSignal):
        """Cognition Journal: Log AI state upon successful trade."""
        entry = {
            "timestamp": time.time(),
            "symbol": symbol,
            "direction": direction,
            "probability": p,
            "kelly_f": f_star,
            "hmm_state": sig.hmm_state,
            "kronos_prob": sig.kronos_prob,
            "xgboost_prob": sig.xgboost_prob,
            "v15_audit": "PASSED"
        }
        try:
            log_file = "cognition_bridge.json"
            history = []
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    history = json.load(f)
            history.append(entry)
            with open(log_file, 'w') as f:
                json.dump(history[-100:], f, indent=4)
        except Exception as e:
            logging.error(f"Failed to log cognition: {e}")

    def execute_panic_sweep(self):
        """P5 Circuit Breaker: Emergency Liquidation"""
        global EMERGENCY_LIQUIDATION
        EMERGENCY_LIQUIDATION = True
        positions = mt5.positions_get()
        if not positions: return
        
        def close_pos(pos):
            tick = mt5.symbol_info_tick(pos.symbol)
            type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": type,
                "position": pos.ticket,
                "price": price,
                "deviation": 9999,
                "magic": 999,
                "comment": "EMERGENCY_LIQUIDATION",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            return mt5.order_send(req)

        with ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(close_pos, positions)
        
        self._save_lockout(24)
        print("!!! EMERGENCY LIQUIDATION COMPLETE. 24-HOUR LOCKOUT INITIATED. !!!")

    def is_rollover_window(self, symbol: str) -> bool:
        """Phase 4: Rollover Blackout (23:55 - 00:15)"""
        tick = mt5.symbol_info_tick(symbol + BROKER_SUFFIX)
        if not tick: return True
        dt = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        current_time_str = dt.strftime('%H:%M')
        if "23:55" <= current_time_str <= "23:59" or "00:00" <= current_time_str <= "00:15":
            return True
        return False

    def has_active_position(self, symbol: str) -> bool:
        """Amnesia Lock: Check for existing directional positions (magic=142)"""
        positions = mt5.positions_get(symbol=symbol + BROKER_SUFFIX)
        if positions:
            for p in positions:
                if p.magic == MAGIC_NUMBER:
                    return True
        return False

    def is_crypto(self, symbol: str) -> bool:
        crypto_keywords = ["BTC", "ETH", "BCH", "LTC", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "UNI"]
        return any(k in symbol.upper() for k in crypto_keywords)

    def check_weekend_sentry(self, symbol: str) -> bool:
        """Phase 4: Weekend Protocol (Friday 23:55 - Monday 00:15)"""
        if self.is_crypto(symbol):
            return False

        # Get broker time via EURUSD (most reliable)
        tick = mt5.symbol_info_tick("EURUSD")
        if not tick: return False
        
        dt = datetime.fromtimestamp(tick.time, tz=timezone.utc)
        weekday = dt.weekday() # 4=Fri, 5=Sat, 6=Sun, 0=Mon
        time_str = dt.strftime('%H:%M')
        
        # 1. Friday Night Blackout (23:55)
        if weekday == 4 and time_str >= "23:55":
            if DEBUG_MODE: print(f"[WEEKEND] Friday 23:55 Blackout active for {symbol}.")
            return True
            
        # 2. Weekend Full Blackout
        if weekday in [5, 6]:
            if DEBUG_MODE: print(f"[WEEKEND] Market Closed for {symbol}.")
            return True
            
        # 3. Monday Morning Blackout (Until 00:15)
        if weekday == 0 and time_str < "00:15":
            if DEBUG_MODE: print(f"[WEEKEND] Monday 00:15 Warmup for {symbol}.")
            return True

        return False

    def check_p5_circuit_breaker(self) -> bool:
        """P5 Circuit Breaker: 15% Max Drawdown Liquidation Gate."""
        acc = mt5.account_info()
        if not acc: return False
        
        # Track Peak Equity
        if not hasattr(self, 'equity_peak'): self.equity_peak = acc.balance
        if acc.equity > self.equity_peak: self.equity_peak = acc.equity
        
        drawdown = (self.equity_peak - acc.equity) / self.equity_peak if self.equity_peak > 0 else 0
        if drawdown >= 0.15:
            print(f"!!! [EMERGENCY] P5 CIRCUIT BREAKER: DRAWDOWN {drawdown:.2%} !!!")
            self.execute_panic_sweep()
            self._save_lockout(24)
            return True
        return False

    def run_fast_loop(self, symbol: str):
        """Perform a single iteration of the MT5 Fast Loop (v16.9)"""
        try:
            # P5 Circuit Breaker: 15% Drawdown Liquidation
            if self.check_p5_circuit_breaker(): return
            
            if time.time() < self._load_lockout():
                with heartbeat_lock: heartbeat_state[symbol] = "P5 LOCKOUT (24H)"
                return
            # Condition 2: Missing Price / Closed Market Check
            # Directive: Suffix-Aware Resolver
            full_symbol = symbol if symbol.endswith(BROKER_SUFFIX) else symbol + BROKER_SUFFIX
            tick = mt5.symbol_info_tick(full_symbol)
            if tick is None:
                self.logger.info(f"[-] {symbol}: Market Closed or Invalid Symbol ({full_symbol})")
                with heartbeat_lock: heartbeat_state[symbol] = "MT5 Closed / No Price"
                return

            start_tick = time.perf_counter()
            audit = ExecutionAudit(symbol=symbol)
            
            # 0. MT5 Watchdog & Lockout
            if not self.watchdog_check(symbol): 
                with heartbeat_lock: heartbeat_state[symbol] = "Watchdog Check Failed"
                return
            
            if time.time() < self.lockout_until:
                with heartbeat_lock: heartbeat_state[symbol] = "System Lockout active"
                return

            # Phase 4: Weekend Sentry check
            if self.check_weekend_sentry(symbol):
                with heartbeat_lock: heartbeat_state[symbol] = "Weekend Sentry Active"
                return

            acc = mt5.account_info()
            if not acc: 
                with heartbeat_lock: heartbeat_state[symbol] = "No Account Info"
                return
            
            # Phase 1: Zero-Latency Sync
            sig = self.fetch_arctic_data(symbol)
            if not sig:
                self.logger.info(f"[-] {symbol}: Rejected (Missing ArcticDB Data)")
                with heartbeat_lock: heartbeat_state[symbol] = "Phase 1: MISSING"
                return
            
            # Check for staleness rejection (v16.9)
            staleness = utils.get_utc_epoch() - sig.timestamp
            if staleness > 360:
                self.logger.info(f"[-] {symbol}: Rejected (Stale ArcticDB Data - {staleness:.1f}s old)")
                with heartbeat_lock: heartbeat_state[symbol] = "Phase 1: STALE_SIGNAL"
                return None

            audit.p1_sync = True
            
            # Phase 3: Memory Audit (Legend Override)
            legend_p, is_legend = self.memory_audit(symbol)
            if is_legend:
                audit.p3_memory = True
                audit.is_legend = True
                audit.final_p = legend_p
                audit.reasoning = "Legend Override"
            
            # Phase 2: Epistemic Gate
            if not audit.is_legend:
                final_p, gate_passed, reason = self.evaluate_epistemic_gate(symbol, sig)
                audit.p2_gate = gate_passed
                audit.final_p = final_p
                audit.reasoning = reason
            
            # Directive 3 (The Sisyphus Cure): Graveyard Check
            is_blocked, graveyard_reason = self.check_graveyard(symbol, sig)
            if is_blocked:
                print(f"[-] {symbol}: {graveyard_reason}")
                with heartbeat_lock: heartbeat_state[symbol] = graveyard_reason
                return

            conviction = abs(audit.final_p - 0.5) + 0.5 # Normalized to 0.5-1.0
            if conviction < 0.82 and not audit.is_legend:
                self.logger.info(f"[-] {symbol}: Rejected (Conviction {audit.final_p:.3f} < 0.82)")
                with heartbeat_lock: heartbeat_state[symbol] = f"Neutral Conviction ({audit.final_p:.3f})"
                return

            if not audit.is_legend and not audit.p2_gate:
                self.logger.info(f"[-] {symbol}: Rejected ({audit.reasoning})")
                with heartbeat_lock: heartbeat_state[symbol] = f"Blocked by {audit.reasoning}"
                return

            # Portfolio Heat Check (20%)
            positions = mt5.positions_get()
            total_risk = sum(abs(p.profit) for p in positions) if positions else 0

            # Leverage Wall (10x)
            # Directive 4: Calculate notional exposure using symbol-specific contract sizes
            total_notional = 0
            if positions:
                for p in positions:
                    p_info = mt5.symbol_info(p.symbol)
                    if p_info:
                        total_notional += p.volume * p.price_open * p_info.trade_contract_size

            # Phase 5: Portfolio Drawdown (15% Circuit Breaker)
            drawdown = (acc.balance - acc.equity) / acc.balance if acc.balance > 0 else 0
            if drawdown >= 0.15:
                print(f"[-] {symbol}: Rejected (P5 Circuit Breaker DD:{drawdown:.2%})")
                with heartbeat_lock: heartbeat_state[symbol] = "P5 Circuit Breaker"
                self.execute_panic_sweep()
                return

            # Directive: Inject Phase 4 Risk Telemetry
            info = mt5.symbol_info(symbol + BROKER_SUFFIX)
            if info:
                direction = "BUY" if audit.final_p > 0.5 else "SELL"
                sl_raw = sig.p10 if direction == "BUY" else sig.p90
                ref_price = info.ask if direction == "BUY" else info.bid
                sl_dist = abs(ref_price - sl_raw)

                p_val = audit.final_p if audit.final_p > 0.5 else (1.0 - audit.final_p)
                q_val = 1.0 - p_val
                f_raw = p_val - (q_val / 1.5)
                f_adj = f_raw * KELLY_FRACTION
                f_final = min(max(0, f_adj), 0.02)
                risk_usd = acc.equity * f_final

                # Lot Size Math
                tick_val = info.trade_tick_value
                tick_size = info.trade_tick_size
                point = info.point
                sl_dist_points = sl_dist / (point + 1e-12)
                point_val = tick_val / (tick_size / point)
                raw_vol = risk_usd / (sl_dist_points * point_val + 1e-12)

                # Identify Rejection Constraints
                rejection_reason = "NONE"
                if f_adj <= 0: rejection_reason = "Kelly <= 0 (Low Edge)"
                if total_risk >= 0.20 * acc.equity: rejection_reason = "Portfolio Heat > 20%"
                if total_notional >= 10.0 * acc.equity: rejection_reason = "Leverage Wall > 10x"
                if self.has_active_position(symbol): rejection_reason = "Amnesia Lock Active"
                if raw_vol < info.volume_min: rejection_reason = f"Lot Size {raw_vol:.4f} < Min {info.volume_min}"

                if rejection_reason != "NONE":
                    self.logger.info(f"[-] {symbol}: Rejected (Risk: {rejection_reason})")
                    with heartbeat_lock: heartbeat_state[symbol] = f"Risk Block: {rejection_reason}"
                    return

                if f_adj > 0.02:
                    if DEBUG_MODE: print(f"[RISK INFO][{symbol}] Kelly capped at 2.0% (Raw: {f_adj:.2%})")
                
                print(f"[RISK AUDIT][{symbol}] $Risk: {risk_usd:.2f} | SL Dist: {sl_dist:.5f} | Raw Vol: {raw_vol:.4f} | F_Adj: {f_adj:.6f}")

            if total_risk < 0.20 * acc.equity and total_notional < 10.0 * acc.equity:
                audit.p4_risk = True

                # Kelly Criterion (f* = p - (q/b))
                p_val = audit.final_p if audit.final_p > 0.5 else (1.0 - audit.final_p)
                q_val = 1.0 - p_val
                b = 1.5
                f_star_raw = p_val - (q_val / b)
                f_star_adj = f_star_raw * KELLY_FRACTION
                audit.f_star = min(max(0, f_star_adj), 0.02)

                if audit.f_star > 0:
                    # Rollover Blackout
                    if self.is_rollover_window(symbol):
                        print(f"[-] {symbol}: Rejected (Rollover Blackout)")
                        with heartbeat_lock: heartbeat_state[symbol] = "Rollover Blackout"
                        return

                    # Phase 2: Regime Alignment (Relaxed)
                    if not audit.is_legend:
                        # BULL -> block SELL, BEAR -> block BUY, RANGE -> ALLOWED
                        if sig.hmm_state == 'BEAR' and audit.final_p > 0.5:
                            print(f"[-] {symbol}: Rejected (Regime Bear/Buy)")
                            with heartbeat_lock: heartbeat_state[symbol] = "Regime Block: BEAR/BUY"
                            return
                        if sig.hmm_state == 'BULL' and audit.final_p < 0.5:
                            print(f"[-] {symbol}: Rejected (Regime Bull/Sell)")
                            with heartbeat_lock: heartbeat_state[symbol] = "Regime Block: BULL/SELL"
                            return
                        # RANGE is now allowed

                    # Amnesia Lock (magic=142)
                    if self.has_active_position(symbol):
                        print(f"[-] {symbol}: Rejected (Amnesia Lock)")
                        with heartbeat_lock: heartbeat_state[symbol] = "Amnesia Lock (Active Pos)"
                        return

                    # Execution Phase 5
                    with heartbeat_lock: heartbeat_state[symbol] = "ARMED - AWAITING EXECUTION"
                    current_sig_time = sig.timestamp
                    last_sig_time = self.last_signals.get(symbol, 0)

                    if current_sig_time > last_sig_time or audit.is_legend:
                        self.route_orders(symbol, audit.f_star, audit.final_p, sig)
                        self.last_signals[symbol] = current_sig_time
                        with heartbeat_lock: heartbeat_state[symbol] = "TRADE EXECUTED"
                        self.logger.info(f"[+] {symbol}: TRADE EXECUTED (Conviction: {audit.final_p:.2f})")

            # Telemetry
            if DEBUG_MODE or audit.f_star > 0:
                self.logger.info(f"[{symbol}] P1:{audit.p1_sync} P2:{audit.p2_gate} P3:{audit.p3_memory} P4:{audit.p4_risk} | P:{audit.final_p:.3f} F_Adj:{audit.f_star:.4f} | {audit.reasoning}")
        except Exception as e:
            self.logger.error(f"Error in fast loop for {symbol}: {e}")

if __name__ == "__main__":
    # Directive 1 (v15.6): Implement OS-Level Singleton Lock
    import socket
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(("127.0.0.1", 65432)) # Unique port for Fast Loop
    except socket.error:
        print("[FATAL] Another instance of Fast Loop (chat_gemma) is already running. Exiting.")
        sys.exit(1)

    print("--- Adaptive Sentinel Execution & Risk Audit (v16.9) ---")
    print("[SYSTEM] Initializing Unified MT5 Connection...")
    
    if not mt5.initialize():
        print("[FATAL] MT5 Initialization failed in main process. Check terminal status.")
        sys.exit(1)
        
    engine = SentinelV15()
    
    print(f"[SYSTEM] Launching ThreadPoolExecutor with 20 workers for {len(WATCHLIST)} assets.")
    print("[SYSTEM] This architectural shift prevents OOM crashes while maintaining high-frequency evaluation.")

    try:
        # Launch Dashboard Thread
        def dashboard_loop():
            while True:
                time.sleep(60)
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"--- ADAPTIVE SENTINEL HEARTBEAT MONITOR | {datetime.now().strftime('%H:%M:%S')} ---")
                print(f"{'SYMBOL':<12} | {'STATUS':<45}")
                print("-" * 60)
                with heartbeat_lock:
                    # Sort by symbol for readability
                    for sym in sorted(heartbeat_state.keys()):
                        print(f"{sym:<12} | {heartbeat_state[sym]:<45}")
                print("-" * 60)
                print(f"[SYSTEM] Monitoring {len(heartbeat_state)} assets. Next update in 60s.")

        dash_thread = threading.Thread(target=dashboard_loop, daemon=True)
        dash_thread.start()

        # Directive 2: Direct-Drive Execution (Sequential)
        # Bypassing ThreadPool to prevent silent background deadlocks under RAM pressure
        streamer = bars.InformationBarStreamer(WATCHLIST)
        
        logging.info("[SYSTEM] Entering Direct-Drive Continuous Evaluation Cycle (Dollar Bars)...")
        for bar in streamer.stream_bars():
            symbol = bar['symbol']
            logging.info(f"[EVALUATING] {symbol} (Bar Yielded)")
            engine.run_fast_loop(symbol)
                
    except KeyboardInterrupt:
        print("[SYSTEM] Shutting down...")
        mt5.shutdown()
        sys.exit(0)
    except Exception as e:
        print(f"[SYSTEM] Critical Error in main execution: {e}")
        mt5.shutdown()
        sys.exit(1)

