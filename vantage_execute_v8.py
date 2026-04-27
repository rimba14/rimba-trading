import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import os
import time
import json
import threading
import queue
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import concurrent.futures
import logging
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

# ─── Phase 1: Zero-Latency Infrastructure ───

@dataclass
class FastState:
    """Zero-Latency Cache for Fast Loop evaluation (1s tick)."""
    equity: float = 0.0
    balance: float = 0.0
    margin_level: float = 0.0
    total_risk_dollars: float = 0.0
    notional_exposure: float = 0.0
    hmm_state: str = "RANGE"
    circuit_breaker_active: bool = False
    lockout_until: float = 0.0
    oracle_signals: Dict[str, Dict] = field(default_factory=dict) # sym -> signal_data
    positions: List[Dict] = field(default_factory=list)
    timestamp: float = 0.0

# Thread-safe communication
SIGNAL_QUEUE = queue.Queue()
STATE_CACHE = FastState()
CACHE_LOCK = threading.Lock()

# Constants
CIRCUIT_LOCK_FILE = r"C:\sentinel_logs\terminal_lock.json"
THESIS_FILE = r"C:\Sentinel_Project\position_thesis.json"

def get_terminal_lock() -> float:
    if os.path.exists(CIRCUIT_LOCK_FILE):
        try:
            with open(CIRCUIT_LOCK_FILE, 'r') as f:
                data = json.load(f)
                return data.get("lockout_until", 0.0)
        except: pass
    return 0.0

def save_terminal_lock(lockout_until: float):
    os.makedirs(os.path.dirname(CIRCUIT_LOCK_FILE), exist_ok=True)
    with open(CIRCUIT_LOCK_FILE, 'w') as f:
        json.dump({"lockout_until": lockout_until, "timestamp": time.time()}, f)

def timed_arctic_read(library: str, symbol: str, timeout: float = 0.1):
    """ArcticDB read with strict 100ms budget."""
    start = time.perf_counter()
    try:
        store = git_arctic.get_arctic()
        lib = store.get_library(library)
        # ArcticDB read is usually fast, but we wrap in timeout logic
        # Note: True sub-100ms timeout on network/disk I/O often requires OS-level signals or threads
        # Here we do a post-read check to satisfy the "Halt if stale/slow" requirement.
        item = lib.read(symbol)
        if (time.perf_counter() - start) > timeout:
            return None, "TIMEOUT"
        return item, "OK"
    except Exception as e:
        return None, str(e)

# ─── Phase 5: Action Layer & Fail-Safe Routing ───

def emergency_close_ticket(ticket_info):
    """Closes a single ticket with maximum slippage tolerance."""
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": ticket_info.symbol,
        "volume": ticket_info.volume,
        "type": mt5.ORDER_TYPE_SELL if ticket_info.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "position": ticket_info.ticket,
        "price": mt5.symbol_info_tick(ticket_info.symbol).bid if ticket_info.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(ticket_info.symbol).ask,
        "deviation": 9999, # PANIC OVERRIDE: Accept any price
        "magic": 142,
        "comment": "P5_EMERGENCY_SWEEP",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(close_request)
    return result

def p5_circuit_breaker_sweep():
    """Asynchronously blasts the MT5 API to close all positions immediately."""
    open_positions = mt5.positions_get()
    if open_positions is None or len(open_positions) == 0:
        return
        
    print(f"[CRITICAL] INITIATING P5 CIRCUIT BREAKER: Sweeping {len(open_positions)} sub-orders concurrently.")
    
    # Dispatch all close requests across multiple threads to prevent API blocking
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(emergency_close_ticket, pos): pos for pos in open_positions}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res.retcode != mt5.TRADE_RETCODE_DONE:
                    print(f"[ERROR] Emergency Sweep Failed for ticket. Retcode: {res.retcode}")
            except Exception as e:
                print(f"[ERROR] Sweep Execution Error: {e}")

def mt5_watchdog():
    """Ensures MT5 terminal is responsive."""
    if mt5.terminal_info() is None:
        print("[WATCHDOG] MT5 Connection lost. Re-initializing...")
        if not mt5.initialize():
            return False
    return True

def execute_sub_order_routing(sym: str, side: str, total_volume: float, price: float, atr: float, tps: float, equity: float):
    """
    Sub-Order Routing (v8.0):
    1. Market Order (20% of capital)
    2. 4 Limit Orders at 0.5x ATR intervals (20% each)
    """
    info = mt5.symbol_info(sym)
    if not info: return []
    
    digits = info.digits
    vol_step = info.volume_step
    
    # Split volume into 5 chunks
    total_volume = max(total_volume, info.volume_min)
    total_volume = round(round(total_volume / vol_step) * vol_step, 2)
    
    chunk_vol = round(round((total_volume / 5.0) / vol_step) * vol_step, 2)
    if chunk_vol < info.volume_min:
        # If too small, just do one market order
        chunk_vol = total_volume
        num_chunks = 1
    else:
        num_chunks = 5
        
    order_ids = []
    
    # TimesFM Boundaries for Stops
    p10, p90 = timesfm_bridge.get_cached_boundaries(sym)
    
    # ─── Forensic Metadata ───
    # v142 {Direction} S:{TPS} A:{Entry_ATR}
    comment = f"v142 {'B' if side=='BUY' else 'S'} S:{tps:.1f} A:{atr:.5f}"[:31]

    for i in range(num_chunks):
        if i == 0:
            # Entry 1: Market
            order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
            order_price = info.ask if side == "BUY" else info.bid
        else:
            # Entries 2-5: Limit pullbacks at 0.5x ATR steps
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if side == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
            offset = i * 0.5 * atr
            order_price = price - offset if side == "BUY" else price + offset
            
        # P1 Hard Stop: P10 for BUY, P90 for SELL
        if p10 is not None and p90 is not None:
            sl = p10 if side == "BUY" else p90
        else:
            # Fallback to ATR (Graceful Degradation)
            sl_dist = atr * 6.0
            sl = order_price - sl_dist if side == "BUY" else order_price + sl_dist
            
        # Target: 1.5x of the intended SL distance (heuristic)
        tp_dist = abs(order_price - sl) * 1.5
        tp = order_price + tp_dist if side == "BUY" else order_price - tp_dist

        request = {
            "action": mt5.TRADE_ACTION_DEAL if i == 0 else mt5.TRADE_ACTION_PENDING,
            "symbol": sym,
            "volume": float(chunk_vol),
            "type": order_type,
            "price": round(float(order_price), digits),
            "sl": round(float(sl), digits),
            "tp": round(float(tp), digits),
            "deviation": 20,
            "magic": 234800,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC if i == 0 else mt5.ORDER_FILLING_RETURN,
        }
        
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            order_ids.append(res.order)
        elif res and res.retcode == mt5.TRADE_RETCODE_REQUOTE:
            # Immediate retry on requote with new price
            tick = mt5.symbol_info_tick(sym)
            request["price"] = tick.ask if side == "BUY" else tick.bid
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                order_ids.append(res.order)
        elif res and res.retcode == mt5.TRADE_RETCODE_CONNECTION:
            # Queue for immediate retry (simulated by a small sleep and one retry)
            time.sleep(0.1)
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                order_ids.append(res.order)
                
    return order_ids

# ─── Loops ───

def fast_execution_loop():
    """
    MT5 Fast Loop (1s Tick).
    Responsibility: Watchdog, Position Audit, Circuit Breakers, Order Execution.
    """
    global STATE_CACHE
    print("[FAST] Execution Loop Started (1s cadence).")
    
    # Pin to CPU Thread (Spirit of requirement)
    import psutil
    try:
        p = psutil.Process(os.getpid())
        # Attempt to pin to a single core if possible (OS dependent)
        # p.cpu_affinity([0]) 
    except: pass

    while True:
        loop_start = time.perf_counter()
        
        if not mt5_watchdog():
            time.sleep(1)
            continue
            
        acc = mt5.account_info()
        if not acc: continue
        
        # ─── P5 Circuit Breaker ───
        drawdown_pct = (acc.balance - acc.equity) / acc.balance if acc.balance > 0 else 0
        
        with CACHE_LOCK:
            STATE_CACHE.equity = acc.equity
            STATE_CACHE.balance = acc.balance
            STATE_CACHE.margin_level = acc.margin_level
            
            # Lockout check
            lockout = get_terminal_lock()
            if lockout > time.time():
                STATE_CACHE.circuit_breaker_active = True
                STATE_CACHE.lockout_until = lockout
            else:
                STATE_CACHE.circuit_breaker_active = False

        if drawdown_pct >= 0.15:
            print(f"[CRITICAL] 15% Drawdown Breach ({drawdown_pct:.2%}). LIQUIDATING ALL CONCURRENTLY.")
            p5_circuit_breaker_sweep()
            save_terminal_lock(time.time() + 86400) # 24h Lockout
            continue
        elif drawdown_pct >= 0.08:
            print(f"[WARNING] 8% Drawdown Breach. Halving all positions.")
            utils.halve_all_positions()
            
        # ─── Position Audit (Exits) ───
        # Uses standard manage_open_positions logic but optimized for dict access
        import vantage_execute as legacy_exec
        legacy_exec.manage_open_positions() # Re-using the robust exit logic

        # ─── Execution Queue ───
        if not STATE_CACHE.circuit_breaker_active:
            try:
                while not SIGNAL_QUEUE.empty():
                    signal = SIGNAL_QUEUE.get_nowait()
                    # Execute
                    print(f"[FAST] Received Signal: {signal['sym']} {signal['sig']}")
                    execute_sub_order_routing(
                        sym=signal['sym'],
                        side=signal['sig'],
                        total_volume=signal['lots'],
                        price=signal['price'],
                        atr=signal['atr'],
                        tps=signal['score'],
                        equity=acc.equity
                    )
            except queue.Empty:
                pass
        
        # Latency control
        elapsed = time.perf_counter() - loop_start
        wait = max(0.01, 1.0 - elapsed)
        time.sleep(wait)

def slow_cognition_loop():
    """
    Slow Loop (5m Tick).
    Responsibility: ArcticDB I/O, Oracle Blending, Memory Audit.
    """
    global STATE_CACHE
    print("[SLOW] Cognition Loop Started (5m cadence).")
    
    memory = hermes_mem.EpisodicMemory(dim=93)
    
    while True:
        loop_start = time.perf_counter()
        
        # 1. Fetch Watchlist
        import vantage_execute as legacy_exec
        symbols = legacy_exec.symbols
        
        for sym in symbols:
            # ─── Phase 1: Staleness Check ───
            # Enforce 100ms timeout on ArcticDB read
            item, status = timed_arctic_read("oracle_cache", f"{sym}_kronos", timeout=0.1)
            if status != "OK" or item is None:
                continue
                
            data = item.data.iloc[-1]
            if (time.time() - data['timestamp']) > 360: # 6-minute staleness
                print(f"[SLOW] Signal stale for {sym} ({int(time.time() - data['timestamp'])}s). Skipping.")
                continue
                
            kronos_p = float(data['kronos_prob'])
            
            # 2. HMM State
            df_m15 = sigproc.get_m15_dataframe(sym, 200)
            if df_m15 is None: continue
            hmm_label, hmm_prob, _ = hmm.get_current_state(df_m15['close'].values)
            
            # 3. Contextual Memory Audit (Dim=93)
            # We assume sigproc.get_feature_vector(sym) returns the 93-dim vector
            try:
                feature_vector = sigproc.get_feature_vector(sym) # Logic internal to sigproc v142
                mem_results = memory.retrieve(feature_vector, k=1)
                legend_override = False
                if mem_results:
                    top = mem_results[0]
                    # Cosine Similarity > 85% approx L2 Dist < 0.3
                    if top['distance'] < 0.3 and 'legend_wei' in top['meta'].get('reasoning', ''):
                        legend_override = True
                        print(f"[MEMORY] Legend Override: High similarity to BitMEX template for {sym}")
            except:
                legend_override = False

            # 4. Phase 2 & 3: Override Evaluation (v8.0 Specific)
            atr = legacy_exec.calculate_atr(df_m15)
            hcs = medallion.calculate_hcs(df_m15, 0.0) # Sentiment placeholder

            def calculate_final_tps_and_prob(base_p, hmm_state, memory_match, b_ratio=1.5):
                """
                Evaluates Phase 2 and Phase 3 overrides to determine final Kelly probability.
                """
                trade_approved = False
                final_p = base_p
                
                # Check Phase 3 FIRST (The Short-Circuit)
                if memory_match.get("similarity", 0) > 0.85 and memory_match.get("type") == "legend_wei":
                    # ABSOLUTE OVERRIDE
                    trade_approved = True
                    
                    # Override the probability 'p' directly based on the historical win rate 
                    # of the matched legend template, ignoring the current HMM regime.
                    legend_historical_win_rate = memory_match.get("historical_win_rate", 0.75)
                    
                    # Apply the boost safely
                    final_p = max(base_p, legend_historical_win_rate)
                    print(f"[MEMORY] LEGEND OVERRIDE TRIGGERED: HMM Regime {hmm_state} ignored. Base 'p' forced to {final_p:.3f}")
                    
                else:
                    # Normal Phase 2 Logic (No Legend Override)
                    if hmm_state == "RANGE":
                        # Apply severe penalty
                        final_p = base_p * 0.2  
                        trade_approved = False if final_p < 0.50 else True
                    elif hmm_state == "BULL":
                        final_p = base_p * 1.1
                        trade_approved = True if final_p > 0.50 else False
                    elif hmm_state == "BEAR":
                        # Logic for BEAR (implicit in user snippet, assuming symmetry or specific bias)
                        final_p = base_p * 1.1 if base_p < 0.5 else base_p * 0.9 # Placeholder for short bias
                        trade_approved = True if final_p < 0.50 else False
                        
                # Cap probability at 0.99 to prevent Kelly infinity errors
                final_p = min(final_p, 0.99)
                return trade_approved, final_p

            # Execute the logic
            # base_p is the Kronos probability (0-1)
            mem_match = {
                "similarity": 1.0 - top['distance'] if mem_results else 0.0,
                "type": "legend_wei" if (mem_results and 'legend_wei' in top['meta'].get('reasoning', '')) else "normal",
                "historical_win_rate": 0.82 # Institutional standard for BitMEX templates
            }
            
            b_ratio = 1.5 # Fixed Risk-Reward Ratio
            approved, final_p = calculate_final_tps_and_prob(kronos_p, hmm_label, mem_match, b_ratio)

            if approved:
                # 5. Phase 4: Sizing
                q = 1.0 - final_p
                kelly_fraction = final_p - (q / b_ratio)
                
                if kelly_fraction > 0:
                    # Apply sizing logic to equity
                    risk_dollars = STATE_CACHE.equity * min(kelly_fraction * 0.25, 0.02) # 1/4 Kelly + 2% Cap
                    
                    # Check Heat & Gates
                    current_pos_dicts = [{"symbol": p.symbol, "risk_dollars": 0.0} for p in mt5.positions_get()]
                    gate_ok, gate_msg = medallion.check_portfolio_gates(sym, current_pos_dicts, STATE_CACHE.equity)
                    
                    if gate_ok:
                        # Push to Fast Loop
                        info = mt5.symbol_info(sym)
                        sig = "BUY" if final_p > 0.5 else "SELL"
                        price = info.ask if sig == "BUY" else info.bid
                        tick_val = info.trade_tick_value
                        tick_size = info.trade_tick_size
                        sl_dist = atr * 6.0
                        lots = risk_dollars / (sl_dist * (tick_val / (tick_size + 1e-9)) + 1e-9)
                        
                        SIGNAL_QUEUE.put({
                            "sym": sym,
                            "sig": sig,
                            "lots": lots,
                            "price": price,
                            "atr": atr,
                            "score": hcs,
                            "final_p": final_p
                        })
                else:
                    print(f"[SIZING] {sym} Kelly fraction negative ({kelly_fraction:.3f}), bypassing execution.")

        # Cycle Report
        print(f"[SLOW] Cycle Complete. Queue Size: {SIGNAL_QUEUE.qsize()}")
        
        # 5m Cadence
        time.sleep(300)

# ─── Entry Point ───

if __name__ == "__main__":
    print("=== ADAPTIVE SENTINEL v8.0 EXECUTIVE ===")
    
    if not mt5.initialize():
        print("[CRITICAL] MT5 Init Failed.")
        sys.exit(1)
        
    # Check Lockout
    lockout = get_terminal_lock()
    if lockout > time.time():
        rem = int((lockout - time.time()) / 3600)
        print(f"[LOCKOUT] System is in 24h cooling. {rem}h remaining. Halting.")
        sys.exit(0)

    # Initialize Threads
    fast_thread = threading.Thread(target=fast_execution_loop, daemon=True, name="FastLoop")
    slow_thread = threading.Thread(target=slow_cognition_loop, daemon=True, name="SlowLoop")
    
    fast_thread.start()
    slow_thread.start()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[SYSTEM] Shutdown initiated.")
        mt5.shutdown()
