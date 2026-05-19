"""
fastapi_sniper.py - Adaptive Sentinel Direct HTTP Execution Bridge (Machine B)
Ultra-Low-Latency, WebSocket-Free MT5 Execution Node (v28.30 - Ironclad CADES (Delayed Fortress Exit))
Concurrency: Idempotent Execution & Mutex Locking Active.
v24.2: Upgraded baseline to Volume-Weighted Micro-Price & Regime-Aware Squashing.
"""

import os
import json
import math
import time
import logging
import sys
import io

# Force UTF-8 armor on standard outputs to absolutely prevent charmap encoding errors
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import uvicorn
import MetaTrader5 as mt5
from dotenv import load_dotenv
import requests
import numpy as np
from constants import AGENT_SIGNATURE
from capital_wall import CapitalWall, TradeRejected

risk_session = requests.Session()
# Load constitution/config
sys.path.append(r"C:\Sentinel_Project")
from sentinel_config import (
    WATCHLIST, KELLY_FRACTION, PORTFOLIO_HEAT_CAP, 
    LEVERAGE_WALL, STALENESS_THRESHOLD, EPISTEMIC_GATE, 
    MAGIC_NUMBER, HARD_RISK_CAP, AC_LARGE_ORDER_THRESHOLD
)

load_dotenv()

# Configure Logging — v27.0: Centralized via logger_config.py
import io
os.environ["PYTHONIOENCODING"] = "utf-8"
def _get_utf8_stream():
    if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
        return sys.stdout
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except Exception:
        return io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

_UTF8_STREAM = _get_utf8_stream()
LOG_FILE = r"C:\sentinel_logs\fastapi_sniper_v2.log"
_LOG_FMT = '%(asctime)s [HTTP_SNIPER] %(message)s'

# v27.0: Removed logging.basicConfig() — rely on named logger to prevent duplicate outputs
logger = logging.getLogger("HttpSniper")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_LOG_FMT))
    logger.addHandler(fh)
    sh = logging.StreamHandler(_UTF8_STREAM)
    sh.setFormatter(logging.Formatter(_LOG_FMT))
    logger.addHandler(sh)

# FastAPI App Initialization
app = FastAPI(title="Adaptive Sentinel HTTP Sniper")

# Directive 1 & 2: Level 14 SRE Refactoring - Native MT5 Ledger Amnesia Lock
from datetime import timedelta

def is_amnesia_lock_active(symbol, cooldown_seconds=86400):
    # v26.0 Swing Paradigm: 24-hour post-exit embargo (86400s).
    # Swing setups take days to form; re-entering minutes after a stop-loss is statistically invalid noise.
    info = mt5.symbol_info(symbol)
    if not info: 
        return False
    current_broker_time = info.time
    
    # Fetch history deals for the last 2 days (generous window for 24h embargo)
    now = datetime.now()
    lookback = now - timedelta(days=2)
    tomorrow = now + timedelta(days=1)
    
    # Filter deals SPECIFICALLY for this symbol
    deals = mt5.history_deals_get(lookback, tomorrow, group=f"*{symbol}*")
    
    if deals is None or len(deals) == 0:
        return False # No recent trades, clear to execute
        
    # Find the absolute most recent deal timestamp
    last_deal_time = max([deal.time for deal in deals])
    
    # Enforce the 24-hour embargo using unified broker time
    time_since_last_trade = current_broker_time - last_deal_time
    
    if 0 <= time_since_last_trade < cooldown_seconds:
        return True # Lock Active for this specific symbol!
        
    return False # Clear to execute

def enforce_stoplevel_and_normalize(symbol, current_price, target_price, is_sl, is_buy):
    """v25.1: Level 29 SRE Stoplevel Armor & Tick Normalization."""
    info = mt5.symbol_info(symbol)
    if not info: return target_price
    
    tick_size = info.trade_tick_size
    point = info.point
    # trade_stops_level is in points. convert to price distance.
    stoplevel_distance = info.trade_stops_level * point
    
    # Directive 1: Enforce Minimum Distance (Stoplevel)
    if is_buy:
        if is_sl: # Buy SL must be BELOW (current_price - stoplevel)
            max_allowed_sl = current_price - stoplevel_distance
            target_price = min(target_price, max_allowed_sl)
        else:     # Buy TP must be ABOVE (current_price + stoplevel)
            min_allowed_tp = current_price + stoplevel_distance
            target_price = max(target_price, min_allowed_tp)
    else: # SELL
        if is_sl: # Sell SL must be ABOVE (current_price + stoplevel)
            min_allowed_sl = current_price + stoplevel_distance
            target_price = max(target_price, min_allowed_sl)
        else:     # Sell TP must be BELOW (current_price - stoplevel)
            max_allowed_tp = current_price - stoplevel_distance
            target_price = min(target_price, max_allowed_tp)
            
    # Directive 2: Strict Tick Size Normalization
    if tick_size > 0:
        normalized_price = round(target_price / tick_size) * tick_size
    else:
        normalized_price = target_price
    return round(normalized_price, info.digits)

def atomic_sl_tp_modification(pos, new_sl, new_tp):
    """
    v27.0: Level 42 SRE Atomic Modification Block.
    Retries SL/TP attachment 3 times. If all fail, fires the Naked Kill Switch.
    """
    max_retries = 3
    attempt = 0
    result = None
    
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": pos.ticket,
        "sl": new_sl,
        "tp": new_tp
    }
    
    while attempt < max_retries:
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[MT5 SUCCESS] Ticket {pos.ticket} SL/TP attached flawlessly (Attempt {attempt+1}).")
            return True
        
        attempt += 1
        if attempt < max_retries:
            logger.warning(f"[WARN] [MT5 RETRY] Ticket {pos.ticket} SL/TP mod failed (Retcode: {result.retcode if result else 'None'}). Retrying in 250ms (Attempt {attempt}/{max_retries})...")
            time.sleep(0.25)
            
    # IF WE REACH HERE, ALL RETRIES FAILED. FIRE THE NAKED KILL SWITCH.
    logger.critical(f"[ALERT] [CRITICAL] SL/TP modification failed after 3 retries for Ticket {pos.ticket}. Firing Emergency Naked Kill Switch.")
    
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        logger.error(f"[FATAL] Cannot kill ticket {pos.ticket} - No tick data.")
        return False
        
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
    
    kill_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": pos.ticket,
        "price": close_price,
        "deviation": 30,
        "magic": MAGIC_NUMBER,
        "comment": "NAKED_KILL_SWITCH",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    kill_res = mt5.order_send(kill_request)
    if kill_res and kill_res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[KILL] [NAKED KILL] Successfully liquidated orphan Ticket {pos.ticket} at market.")
    else:
        logger.error(f"[FAIL] [NAKED KILL FAIL] Ticket {pos.ticket} liquidation failed! Retcode: {kill_res.retcode if kill_res else 'None'}")
        
    return False

active_liquidations = set()

class TradeSignal(BaseModel):
    symbol: str
    direction: str
    conviction: Optional[float] = 0.80
    xgb_p: float = 0.5
    ddqn_p: float = 0.5
    hmm_state: str = "RANGE"
    timestamp: Optional[int] = None
    reasoning: str = ""
    vpin: float = 0.0
    signal_type: str = "UNKNOWN"
    rsi: Optional[float] = None
    data_quality_flag: str = "PRISTINE"
    alpha_features: Optional[dict] = None
    vrs: Optional[float] = 1.0
    applied_dynamic_gate: Optional[float] = None
    strategy_type: Optional[str] = "MOMENTUM"
    sl: Optional[float] = 0.0
    tp: Optional[float] = 0.0
    size_multiplier: Optional[float] = 1.0
    tag: Optional[str] = ""

@app.on_event("startup")
def startup_event():
    # v27.0: Boot assertion — MT5 comment field is capped at 31 chars
    assert len(AGENT_SIGNATURE) < 31, f"MT5 Comment exceeds 31 chars: '{AGENT_SIGNATURE}' ({len(AGENT_SIGNATURE)} chars)"
    logger.info(f"[BOOT] Agent Signature verified: '{AGENT_SIGNATURE}' ({len(AGENT_SIGNATURE)} chars)")

    # Tripwire 1: Assert AGENT_SIGNATURE against LEGACY_BANNED list. Exit Code 1 on fail.
    try:
        from sentinel.version_manifest import LEGACY_BANNED
        for banned in LEGACY_BANNED:
            if banned in AGENT_SIGNATURE:
                logger.critical(f"[BOOT TRIPWIRE 1] Legacy signature token detected: {banned} in {AGENT_SIGNATURE}!")
                sys.exit(1)
        logger.info(f"[BOOT TRIPWIRE 1] Signature clean. Banned list cleared.")
    except Exception as e:
        logger.critical(f"[BOOT TRIPWIRE 1] Signature check failed: {e}")
        sys.exit(1)

    # Tripwire 2: Assert sys.stdout.encoding is utf-8. Exit Code 1 on fail.
    encoding = getattr(sys.stdout, 'encoding', '') or ''
    if encoding.lower().replace('-', '') != 'utf8':
        logger.critical(f"[BOOT TRIPWIRE 2] Encoding breach: sys.stdout.encoding is {encoding} (expected UTF-8)!")
        sys.exit(1)
    logger.info("[BOOT TRIPWIRE 2] Encoding verified: UTF-8")

    # Tripwire 3: Use psutil to scan for competing sentinel Python processes. Log a critical warning if sentinel_pids > 0.
    try:
        import psutil
        current_pid = os.getpid()
        competing = []
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                if proc.pid == current_pid:
                    continue
                cmd = proc.info.get('cmdline') or []
                cmd_str = " ".join(cmd)
                # Match sentinel running daemons
                if any(s in cmd_str for s in ['fastapi_sniper.py', 'sentinel_slow_loop.py', 'profit_manager.py']):
                    competing.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if len(competing) > 0:
            logger.critical(f"[BOOT TRIPWIRE 3] WARNING: Competing Sentinel processes detected: PIDs {competing}!")
        else:
            logger.info("[BOOT TRIPWIRE 3] Process dominance verified: No competing Sentinel daemons.")
    except Exception as e:
        logger.warning(f"[BOOT TRIPWIRE 3] Process scan failed: {e}")

    # Tripwire 4: Assert mt5.initialize() succeeds. Exit Code 1 on fail.
    if not mt5.initialize():
        logger.critical("[BOOT TRIPWIRE 4] MT5 Initialization failed. Sniper cannot proceed.")
        sys.exit(1)
    logger.info("[BOOT TRIPWIRE 4] MT5 connection verified.")
    
    # Level 6 SRE Patch: Explicitly subscribe to target portfolio symbols in MT5 Market Watch
    logger.info(f"[BOOT] Forcing MT5 Market Watch selection for {len(WATCHLIST)} portfolio symbols...")
    for sym in WATCHLIST:
        selected = mt5.symbol_select(sym, True)
        if not selected:
            logger.warning(f"[WARN] Failed to select {sym} in MT5 Market Watch.")
            
    # Terminal Status Check
    info = mt5.terminal_info()
    logger.info(f"[BOOT] MT5 Terminal Info: Connected={info.connected} | TradeAllowed={info.trade_allowed}")
    if not info.trade_allowed:
        logger.warning("CRITICAL: MT5 'Algo Trading' button is DISABLED. Enable it in the UI.")
    logger.info("MT5 Initialized. HTTP Sniper online.")

@app.on_event("shutdown")
def shutdown_event():
    mt5.shutdown()
    logger.info("MT5 Shutdown. Sniper offline.")

@app.get("/status")
def status():
    return {
        "status": "online",
        "mt5_connected": mt5.terminal_info() is not None,
        "timestamp": int(time.time()),
        "watchlist_sync": len(WATCHLIST)
    }

@app.post("/execute_trade")
async def execute_trade_endpoint(signal: TradeSignal, request: Request):
    """Securely accepts and executes trade signals from the Oracle Brain."""
    is_fuzzing = request.headers.get("IS_FUZZING") == "True"
    logger.info(f"Received Signal: {signal.symbol} {signal.direction} (P={signal.conviction})")
    
    # --- LEVEL 64 SRE: DRY-FIRE SIMULATION GATES ---
    # Wall 3 Veto: RANGE Regime Momentum Block (Pattern 1)
    if signal.hmm_state == "RANGE" and (signal.rsi is not None and signal.rsi > 50.0):
        logger.warning(f"[{signal.symbol}] [WALL 3 VETO] Pattern 1: Regime Misalignment. Strategy inherently opposed to HMM state.")
        return {"status": "rejected", "reason": "Pattern 1: Regime Misalignment"}
        
    # Wall 9 Veto: Strategy-Regime Congruence
    hmm_regime = "TREND" if signal.hmm_state in ("BULL", "BEAR", "TREND") else "RANGE"
    if signal.strategy_type == "MOMENTUM" and hmm_regime == "RANGE":
        logger.warning(f"[{signal.symbol}] [WALL 9 VETO] Strategy-Regime Congruence: Cannot deploy MOMENTUM strategy in RANGE regime.")
        return {"status": "rejected", "reason": "Wall 9 Veto: Momentum in RANGE regime"}
    elif signal.strategy_type == "MEAN_REVERSION" and hmm_regime == "TREND":
        logger.warning(f"[{signal.symbol}] [WALL 9 VETO] Strategy-Regime Congruence: Cannot deploy MEAN_REVERSION strategy in TREND regime.")
        return {"status": "rejected", "reason": "Wall 9 Veto: Mean-Reversion in TREND regime"}
        
    # Wall 2 Veto: Sealed Hysteresis / Phantom Conviction Block (Pattern 2)
    if signal.conviction is not None and 0.40 <= signal.conviction <= 0.60:
        logger.warning(f"[{signal.symbol}] [WALL 2 VETO] Pattern 2: Sealed Hysteresis (Phantom Conviction)")
        return {"status": "rejected", "reason": "Pattern 2: Sealed Hysteresis Blocked"}
        
    # Wall 2 Veto: Empty Alpha Features Warning (Pattern 4)
    if signal.alpha_features is not None and len(signal.alpha_features) == 0:
        logger.warning(f"[{signal.symbol}] [WALL 2 VETO] Pattern 4: Empty Alpha Features.")
        return {"status": "rejected", "reason": "Pattern 4: Empty Alpha Features Warning"}
        
    # Phase 5 Dry-Fire simulation bypass
    if os.environ.get("SENTINEL_DRY_FIRE") == "1":
        logger.info(f"[{signal.symbol}] Dry-fire simulation pass.")
        return {"status": "success", "symbol": signal.symbol, "lot": 0.01}
        
    # 1. Staleness Check
    ts = signal.timestamp if signal.timestamp is not None else int(time.time())
    staleness = time.time() - ts
    if staleness > STALENESS_THRESHOLD:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: STALE ({staleness:.1f}s old)")
        raise HTTPException(status_code=400, detail="Signal stale")

    # 2. Epistemic Gate (Volatility-Adjusted VAG Gate)
    norm_p = abs(signal.conviction - 0.5) + 0.5
    high_vol_assets = {"NAS100", "US30", "SPX500", "SP500", "GER40", "NAS100.r", "XAUUSD", "XAGUSD", "GOLD", "SILVER"}
    base_gate = 0.72 if signal.symbol.upper() in high_vol_assets else 0.68
    
    # Query active VRS
    vrs = signal.vrs if signal.vrs is not None else 1.0
    
    # Calculate Volatility-Adjusted Gate
    if vrs < 0.8:
        dynamic_gate = base_gate - 0.015
    elif vrs > 1.2:
        dynamic_gate = base_gate + 0.020
    else:
        dynamic_gate = base_gate
        
    dynamic_gate = max(dynamic_gate, 0.65)
    
    target_gate = signal.applied_dynamic_gate if (hasattr(signal, "applied_dynamic_gate") and signal.applied_dynamic_gate is not None) else dynamic_gate
    
    if norm_p < target_gate:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: NormP {norm_p:.3f} < dynamic gate {target_gate:.3f} (Base={base_gate:.2f}, VRS={vrs:.2f})")
        raise HTTPException(status_code=400, detail=f"Epistemic gate block (VAG: {target_gate:.3f})")
        
    logger.info(f"[{signal.symbol}] Signal VALID: NormP {norm_p} >= SlowLoop Gate {target_gate}")

    # 2b. Native MT5 Ledger Amnesia Lock Check (v27.0: 24-hour Embargo)
    if is_amnesia_lock_active(signal.symbol, cooldown_seconds=86400):
        logger.warning(f"[{signal.symbol}] Signal REJECTED: Amnesia Lock Active (24-hour Embargo)")
        raise HTTPException(status_code=429, detail="Amnesia Lock Active (24h)")

    # 2c. Sealed Hysteresis (v28.0 Phase 4: HARD BLOCK 0.40 <= P <= 0.60)
    if 0.40 <= signal.conviction <= 0.60:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: Sealed Hysteresis Block (0.40 <= {signal.conviction} <= 0.60)")
        raise HTTPException(status_code=403, detail="Sealed Hysteresis Block")

    # WALL 3: Regime Alignment Veto (v28.0)
    sig_type_upper = signal.signal_type.upper()
    if signal.hmm_state == "RANGE" and ("MOMENTUM" in sig_type_upper or "BREAKOUT" in sig_type_upper):
        logger.warning(f"[{signal.symbol}] [WALL 3 VETO] Pattern 1: Regime Misalignment. Strategy inherently opposed to HMM state. (RANGE vs {signal.signal_type})")
        raise HTTPException(status_code=403, detail="Regime Misalignment (RANGE vs Momentum)")
    if signal.hmm_state in ["BULL", "BEAR", "TREND"] and "MEAN_REVERSION" in sig_type_upper:
        logger.warning(f"[{signal.symbol}] [WALL 3 VETO] Pattern 1: Regime Misalignment. Strategy inherently opposed to HMM state. ({signal.hmm_state} vs {signal.signal_type})")
        raise HTTPException(status_code=403, detail="Regime Misalignment (TREND vs Mean-Reversion)")

    # 2c. Pre-Trade Toxicity Gating (VPIN)
    vpin_val = getattr(signal, 'vpin', 0.0)
    if vpin_val <= 0.0:
        try:
            vpin_file = Path(f"C:/Sentinel_Project/data/vpin_{signal.symbol}.json")
            if vpin_file.exists():
                with open(vpin_file, "r") as vf:
                    vpin_val = float(json.load(vf).get("vpin", 0.0))
        except Exception:
            pass
            
    if vpin_val > 0.750:
        logger.warning(f"[{signal.symbol}] [WALL 2 VETO] Pattern 6: Toxicity Blindness. Adversarial order flow detected. (VPIN={vpin_val:.3f})")
        raise HTTPException(status_code=429, detail="Order-flow toxicity threshold breached (VPIN > 0.750)")

    # 3. Sizing (Calculate before Risk Gates for accurate validation)
    lot_size = calculate_kelly_lot(signal.symbol, signal.conviction)
    if lot_size <= 0:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: Lot size <= 0")
        raise HTTPException(status_code=400, detail="Invalid lot size")

    # 4. Risk Gates (Now with accurate size)
    tick = mt5.symbol_info_tick(signal.symbol)
    price = tick.ask if signal.direction == "BUY" else tick.bid
    incoming_notional = lot_size * price

    # v28.0 Trade Quality: Enforce CapitalWall Security Gates (Wall 4 & 5)
    wall = CapitalWall()
    try:
        lot_size = wall.run(signal, lot_size, price)
    except TradeRejected as e:
        logger.warning(f"[{signal.symbol}] [CAPITAL WALL VETO] Trade aborted: {e}")
        raise HTTPException(status_code=403, detail=str(e))

    # check_risk_gates now handles its own HTTPException raises for specific reasons
    if not check_risk_gates(signal.symbol, signal.direction, signal.hmm_state, incoming_notional, signal.xgb_p, signal.ddqn_p, signal.conviction):
        return {"status": "rejected", "detail": "Risk gate block"}

    # v23.15 Directive: Pre-Validation Margin Shield / Atomic Mutual Exclusion Execution
    # Logic flows strictly: Signal Received -> Delta P Gate (ΔP) -> Margin Pre-Validation Gate -> If Pass: Liquidate Old Position -> Execute New Position.
    all_positions = mt5.positions_get()
    if all_positions:
        account_info = mt5.account_info()
        for p in all_positions:
            if signal.symbol in p.symbol and p.magic == MAGIC_NUMBER:
                p_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                if p_dir != signal.direction:
                    # Estimate margin required for the incoming trade
                    action_type = mt5.ORDER_TYPE_BUY if signal.direction == "BUY" else mt5.ORDER_TYPE_SELL
                    est_margin = mt5.order_calc_margin(action_type, signal.symbol, lot_size, price)
                    if est_margin is None:
                        est_margin = incoming_notional / 5.0
                        
                    if account_info:
                        margin_free = account_info.margin_free
                        margin_level = account_info.margin_level
                        if (margin_level > 0 and margin_level < 205.0) or est_margin > margin_free:
                            logger.warning(f"[{signal.symbol}] [MARGIN VETO] Mutual Exclusion vetoed: Margin Level ({margin_level:.1f}%) < 205.0% OR Est Margin (${est_margin:.2f}) > Margin Free (${margin_free:.2f}). Blocking inline liquidation.")
                            return {"status": "rejected", "detail": "Mutual Exclusion vetoed by Margin Shield"}
                            
                    logger.info(f"[{signal.symbol}] Triggering Pre-Validated Mutual Exclusion exit for ticket #{p.ticket}")
                    execute_exit(p.ticket, p.symbol, "Mutual Excl")

    # 5. Execution
    alpha_features = {
        "P": signal.conviction,
        "vpin": vpin_val,
        "regime": signal.hmm_state,
        "xgb_p": signal.xgb_p,
        "ddqn_p": signal.ddqn_p,
        "data_quality_flag": signal.data_quality_flag,
        "vrs": signal.vrs if signal.vrs is not None else 1.0,
        "is_fuzzing": is_fuzzing,
        "strategy_type": signal.strategy_type
    }
    success = perform_mt5_trade(
        signal.symbol,
        signal.direction,
        lot_size,
        signal.conviction,
        vpin=vpin_val,
        alpha_features=alpha_features
    )
    if success:
        return {"status": "success", "symbol": signal.symbol, "lot": lot_size}
    else:
        raise HTTPException(status_code=500, detail="MT5 execution failed")

@app.post("/liquidate")
async def liquidate_endpoint(request: Request):
    """Accepts liquidation signals from the Profit Manager or Deep Research Oracle."""
    data = await request.json()
    symbol = data.get("symbol")
    reason = data.get("reason", "Thesis Decay")
    
    if symbol == "*":
        logger.critical(f"GLOBAL LIQUIDATION TRIGGERED. Reason: {reason}")
        positions = mt5.positions_get()
        if positions:
            for p in positions:
                execute_exit(p.ticket, p.symbol, reason)
        return {"status": "global_liquidation_complete"}
    
    ticket = data.get("ticket")
    
    # Concurrency Lock: Check if ticket is already being processed
    if ticket in active_liquidations:
        logger.info(f"[IDEMPOTENT] Ticket {ticket} is currently locked for liquidation. Ignoring redundant request.")
        return {"status": "ignored", "message": "Ticket currently locked for liquidation"}

    active_liquidations.add(ticket)
    try:
        logger.info(f"Received EXIT Signal: {symbol} Ticket {ticket} Reason: {reason}")
        if execute_exit(ticket, symbol, reason):
            return {"status": "exited", "ticket": ticket}
        else:
            raise HTTPException(status_code=500, detail="Liquidation failed")
    finally:
        if ticket in active_liquidations:
            active_liquidations.remove(ticket)

# -- Helper Logic (Ported from v17.9) ---------------------------------------- 

def extract_conviction_from_comment(comment: str) -> float:
    if not comment:
        return 0.5
    try:
        idx = comment.rfind("_P")
        if idx != -1:
            val_str = comment[idx+2:]
            clean_str = ""
            for c in val_str:
                if c.isdigit() or c == '.':
                    clean_str += c
                else:
                    break
            if clean_str:
                return float(clean_str)
    except Exception:
        pass
    return 0.5

def check_risk_gates(symbol, direction, hmm_state, incoming_notional, xgb_p=0.5, ddqn_p=0.5, conviction=0.5):
    # A. Weekend Blackout
    if is_weekend_blackout(symbol):
        logger.warning(f"[{symbol}] Signal REJECTED: Weekend Blackout")
        return False

    # B. HMM Regime Alignment
    if hmm_state == "BEAR" and direction == "BUY":
        logger.warning(f"[{symbol}] Signal REJECTED: Regime/Direction Mismatch (BEAR/BUY)")
        return False
    if hmm_state == "BULL" and direction == "SELL":
        logger.warning(f"[{symbol}] Signal REJECTED: Regime/Direction Mismatch (BULL/SELL)")
        return False

    # C. Active Position / Delta Gating Check
    all_positions = mt5.positions_get()
    if all_positions:
        opposing_positions = []
        for p in all_positions:
            if symbol in p.symbol and p.magic == MAGIC_NUMBER:
                p_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                if p_dir == direction:
                    logger.warning(f"[{symbol}] Signal REJECTED: Amnesia Lock Active (Same-Direction Position Exists)")
                    return False
                else:
                    opposing_positions.append(p)
        
        if opposing_positions:
            # v23.12 Directive: Conviction Delta Gating (ΔP)
            p_old = 0.5
            for p in opposing_positions:
                extracted = extract_conviction_from_comment(p.comment)
                if abs(extracted - 0.5) > abs(p_old - 0.5):
                    p_old = extracted
            
            incoming_delta = abs(conviction - 0.5)
            old_delta = abs(p_old - 0.5)
            # Enforce a mandatory minimum threshold buffer (+0.05) to prevent high-frequency amnesia chatter sweeps
            if incoming_delta < old_delta + 0.05:
                logger.warning(f"[{symbol}] Signal REJECTED by Conviction Delta Gate: Incoming |P-0.5| ({incoming_delta:.4f}) < Active |P-0.5| + 0.05 ({old_delta + 0.05:.4f})")
                return False
            logger.info(f"[{symbol}] Conviction Delta Gate Passed: Incoming |P-0.5| ({incoming_delta:.4f}) >= Active |P-0.5| + 0.05 ({old_delta + 0.05:.4f}). Authorized for Mutual Exclusion.")

    # D. MCP Risk Agent Check (v22.8) — v27.0 Circuit Breaker
    try:
        risk_url = "http://localhost:8001/check_trade"
        payload = {
            "symbol": symbol,
            "size_usd": incoming_notional,
            "leverage": 5,
            "xgb_p": xgb_p,
            "ddqn_p": ddqn_p
        }
        resp = risk_session.post(risk_url, json=payload, timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("allow"):
                logger.warning(f"[{symbol}] Signal REJECTED by MCP Risk Agent: {data.get('reason')}")
                return False
            logger.info(f"[{symbol}] MCP Risk Agent Authorized Trade.")
        elif resp.status_code == 403:
            err_reason = resp.json().get("detail", "Risk Agent Veto")
            logger.warning(f"[{symbol}] Risk Agent 403 VETO: {err_reason}")
            return False
        else:
            logger.critical(f"[{symbol}] [RISK AGENT FAILURE] Unexpected status {resp.status_code}. Trade REJECTED (circuit breaker).")
            return False
    except requests.exceptions.Timeout:
        logger.critical(f"[{symbol}] [RISK AGENT FAILURE] Timeout after 2s. Trade REJECTED (circuit breaker).")
        return False
    except Exception as e:
        logger.critical(f"[{symbol}] [RISK AGENT FAILURE] Connection Error: {e}. Trade REJECTED (circuit breaker).")
        return False

    # E. Margin & Leverage Check (Phase 4 - Leverage Wall <= 10x)
    acc = mt5.account_info()
    if acc:
        if acc.margin_level > 0 and acc.margin_level < 200.0:
            logger.warning(f"[{symbol}] Signal REJECTED: Margin Level too low ({acc.margin_level})")
            return False
    
    # E. Portfolio Heat Check (Phase 4 - <= 20%)
    positions = mt5.positions_get()
    if positions:
        total_risk = 0.0
        for p in positions:
            # Simple risk proxy: 1% of notional per trade
            s_info = mt5.symbol_info(p.symbol)
            if s_info:
                total_risk += p.volume * s_info.bid * 0.01
        
        if acc and acc.equity > 0 and (total_risk / acc.equity) > PORTFOLIO_HEAT_CAP:
            logger.warning(f"[{symbol}] Signal REJECTED: Portfolio Heat Cap Exceeded ({total_risk/acc.equity:.2%})")
            return False

    return True

# --- DIRECTIVE OMEGA HELPERS & LAYER 5 COMPOSITE PRE-FLIGHT CHECKLIST ---

def is_in_jpy_blackout() -> bool:
    """Check if JPY pairs open hour blackout is active (Rule 6.2)."""
    now_utc = datetime.now(timezone.utc)
    now_mins = now_utc.hour * 60 + now_utc.minute
    # Tokyo Open: 00:00 UTC, London Open: 07:00 UTC, NY Open: 13:30 UTC
    for target in [0, 420, 810]:
        diff = abs(now_mins - target)
        diff = min(diff, 1440 - diff)
        if diff <= 15: # +/- 15 mins
            return True
    return False

def is_in_metals_macro_blackout(symbol: str) -> bool:
    """Check if Metals USD macro release blackout is active (Rule 6.3)."""
    sym_upper = symbol.upper()
    metals = {"XAUUSD", "XAGUSD", "GOLD", "SILVER", "XPTUSD", "XPDUSD"}
    if sym_upper not in metals:
        return False
        
    try:
        macro_path = Path("C:/Sentinel_Project/data/macro_state.json")
        if macro_path.exists():
            with open(macro_path, "r") as f:
                m_state = json.load(f)
                events = m_state.get("upcoming_events", [])
                now_ts = time.time()
                for ev in events:
                    ev_time = ev.get("time", 0)
                    impact = ev.get("impact", "").upper()
                    currency = ev.get("currency", "").upper()
                    if currency == "USD" and impact in ["HIGH", "TIB-1", "TIER-1"]:
                        if abs(now_ts - ev_time) <= 15 * 60: # +/- 15 mins
                            return True
    except Exception:
        pass
    return False

# Dynamic Liquidity-Tiered Event Horizons (v28.15 Rule)
MACRO_BLACKOUT_TIERS = {
    # Tier 1: Highly Liquid Majors & Indices & Gold (12-Hour Blackout)
    "EURUSD": 12.0, "USDJPY": 12.0, "GBPUSD": 12.0, "XAUUSD": 12.0,
    "GOLD": 12.0, "SP500": 12.0, "NAS100": 12.0, "US30": 12.0,
    "GER40": 12.0, "FRA40": 12.0, "BTCUSD": 12.0, "ETHUSD": 12.0,
    "US2000": 12.0, "SPX500": 12.0,
    
    # Tier 2: Moderate Liquidity Minors & Silver (18-Hour Blackout)
    "AUDUSD": 18.0, "USDCAD": 18.0, "NZDUSD": 18.0, "USDCHF": 18.0,
    "XAGUSD": 18.0, "SILVER": 18.0, "SOLUSD": 18.0, "XRPUSD": 18.0,
    "LTCUSD": 18.0,
}

def is_wall5_macro_blackout(symbol: str) -> Tuple[bool, str]:
    """
    Directive Omega: Wall 5 / Ex-Ante Macro Shield (Rule 5).
    Enforces dynamic Liquidity-Tiered Blackout gates for G8 basket.
    """
    sym_upper = symbol.upper()
    currencies_to_check = set()
    
    # 1. Parse/Split currencies (EURUSD -> EUR, USD)
    metals = {"XAUUSD", "XAGUSD", "GOLD", "SILVER"}
    if any(m in sym_upper for m in metals):
        currencies_to_check.add("USD")
    elif len(sym_upper) == 6 and not any(c.isdigit() for c in sym_upper):
        currencies_to_check.add(sym_upper[:3])
        currencies_to_check.add(sym_upper[3:])
    else:
        # Default index/crypto mapping
        if any(idx in sym_upper for idx in ["NAS100", "US30", "SP500", "SPX500", "US2000", "BTC", "ETH", "SOL", "XRP"]):
            currencies_to_check.add("USD")
        elif "GER40" in sym_upper:
            currencies_to_check.add("EUR")
        else:
            currencies_to_check.add("USD")
            
    # 2. Determine liquidity-tiered blackout horizon (Rule 5)
    blackout_hours = MACRO_BLACKOUT_TIERS.get(sym_upper, 24.0) # Tier 3 defaults to 24.0 hours
            
    # 3. Iterate through macro calendar in macro_state.json
    try:
        macro_path = Path("C:/Sentinel_Project/data/macro_state.json")
        if macro_path.exists():
            with open(macro_path, "r", encoding="utf-8") as f:
                m_state = json.load(f)
                events = m_state.get("upcoming_events", [])
                now_ts = time.time()
                for ev in events:
                    ev_time = ev.get("time", 0)
                    impact = ev.get("impact", "").upper()
                    currency = ev.get("currency", "").upper()
                    event_name = ev.get("event", "")
                    
                    if currency in currencies_to_check and impact == "HIGH":
                        time_until = ev_time - now_ts
                        if 0 < time_until <= blackout_hours * 3600: # Dynamic Tier Blackout
                            hours_until = time_until / 3600.0
                            msg = f"[WALL 5 VETO] {symbol} blocked due to Tier-1 {currency} Event ({event_name}) in {hours_until:.1f} hours (Tier Limit: {blackout_hours}h)."
                            logger.warning(msg)
                            return True, msg
    except Exception as e:
        logger.warning(f"[WALL 5 SHIELD ERR] Failed to parse macro shield: {e}")
        
    return False, ""

def get_daily_drawdown() -> float:
    """Calculate daily drawdown relative to starting balance and peak equity of the day (Rule 7.1)."""
    acc = mt5.account_info()
    if not acc:
        return 0.0
    try:
        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(today_start, now_utc)
        
        today_profit = 0.0
        if deals:
            for d in deals:
                if d.entry == mt5.DEAL_ENTRY_OUT:
                    today_profit += d.profit
                    
        start_bal = acc.balance - today_profit
        peak_equity = max(start_bal, acc.equity)
        drawdown = (peak_equity - acc.equity) / peak_equity if peak_equity > 0 else 0.0
        return drawdown
    except Exception:
        return 0.0

def get_consecutive_losses() -> int:
    """Calculate the number of consecutive losing trades for Sentinel (Rule 7.2)."""
    try:
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=2), now)
        if not deals:
            return 0
        sentinel_deals = [d for d in deals if d.magic in [MAGIC_NUMBER, 142, 17300] and d.entry == mt5.DEAL_ENTRY_OUT]
        sentinel_deals.sort(key=lambda x: x.time, reverse=True)
        
        consec_losses = 0
        for d in sentinel_deals:
            if d.profit < 0:
                consec_losses += 1
            else:
                break
        return consec_losses
    except Exception:
        return 0

def is_consec_losses_paused() -> Tuple[bool, float]:
    """Check if the SRE Hard Pause is active due to >= 3 consecutive losses (Rule 7.2)."""
    try:
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=2), now)
        if not deals:
            return False, 0.0
        sentinel_deals = [d for d in deals if d.magic in [MAGIC_NUMBER, 142, 17300] and d.entry == mt5.DEAL_ENTRY_OUT]
        sentinel_deals.sort(key=lambda x: x.time, reverse=True)
        
        consec_losses = 0
        last_loss_time = 0
        for d in sentinel_deals:
            if d.profit < 0:
                consec_losses += 1
                if last_loss_time == 0:
                    last_loss_time = d.time
            else:
                break
                
        if consec_losses >= 3:
            elapsed = time.time() - last_loss_time
            if elapsed < 4 * 3600:
                return True, (4 * 3600 - elapsed)
    except Exception:
        pass
    return False, 0.0

def run_composite_preflight_checklist(
    symbol: str,
    direction: str,
    lot: float,
    conviction: float,
    vpin: float,
    hmm_state: str,
    xgb_p: float,
    ddqn_p: float,
    payload: dict = None,
) -> Tuple[bool, str]:
    """
    Directive Omega: Layer 5 - Composite Pre-Flight Checklist.
    Verifies 20 critical protections before dispatching order.
    """
    logger.info(f"[{symbol}] Running 20-point Composite Pre-Flight Checklist...")

    # Point 1: Sizing > 0
    if float(lot) <= 0.0:
        return False, "Point 1 Fail: Sizing <= 0 (Zero-Sizing Veto)"

    # Point 2: Affordability Check
    acc = mt5.account_info()
    info = mt5.symbol_info(symbol)
    if acc is None or info is None:
        return False, "Point 2 Fail: Failed to fetch account/symbol info"

    current_atr, _ = calculate_atr_and_swing(symbol, direction, lookback=20)
    point_val = info.trade_tick_value / (info.trade_tick_size / info.point) if info.trade_tick_size > 0 else info.trade_tick_value
    risk_budget = acc.balance * 0.02
    affordable_lot = risk_budget / (current_atr * point_val * 3.0 + 1e-12)
    if float(affordable_lot) < float(info.volume_min):
        return False, f"Point 2 Fail: Affordability pre-screen check failed ({affordable_lot:.4f} < broker min {info.volume_min})"

    # Point 3: Data Quality Flag Assertion (Strict String Match)
    data_quality_flag = "PRISTINE"
    vrs = 1.0
    if payload is not None and isinstance(payload, dict):
        data_quality_flag = payload.get("data_quality_flag", "UNKNOWN")
        vrs = payload.get("vrs", 1.0)
    
    if data_quality_flag != "PRISTINE":
        if data_quality_flag == "DEGRADED":
            norm_p = abs(conviction - 0.5) + 0.5
            is_stable_vrs = (vrs <= 1.2)
            if norm_p >= 0.85 and is_stable_vrs:
                logger.info(f"[{symbol}] [DATA_QUALITY_BYPASS] Allowing DEGRADED data for high conviction signal (NormP={norm_p:.3f} >= 0.85, VRS={vrs:.2f} stable)")
            else:
                return False, f"Point 3 Fail: [HARD_VETO] [DATA_QUALITY_VETO] Data quality is {data_quality_flag} (expected PRISTINE, or NormP >= 0.85 with stable VRS)"
        else:
            return False, f"Point 3 Fail: [HARD_VETO] [DATA_QUALITY_VETO] Data quality is {data_quality_flag} (expected PRISTINE)"

    # Point 4: Ingestion Data Degraded (ATR Check)
    if float(current_atr) <= 0.0:
        return False, "Point 4 Fail: Ingestion data degraded (ATR <= 0)"

    # Point 5: P_blend Threshold (Volatility-Adjusted VAG Gate)
    norm_p = abs(conviction - 0.5) + 0.5
    high_vol_assets = {"NAS100", "US30", "SPX500", "SP500", "GER40", "NAS100.r", "XAUUSD", "XAGUSD", "GOLD", "SILVER"}
    
    # Retrieve tick starvation flag from slow loop module if active
    is_starved = False
    if "sentinel_slow_loop" in sys.modules:
        try:
            is_starved = (getattr(sys.modules["sentinel_slow_loop"], "_TICK_STARVATION_DETECTED", False) == True)
        except Exception:
            pass
        
    if is_starved == True:
        min_p = 0.75
    elif symbol.upper() in high_vol_assets:
        min_p = 0.72
    else:
        min_p = 0.68
        
    # Query Volatility Regime Score (VRS) from payload
    vrs = 1.0
    if payload is not None and isinstance(payload, dict):
        vrs = payload.get("vrs", payload.get("alpha_features", {}).get("vrs", 1.0))
        
    # Calculate Volatility-Adjusted Gate
    if vrs < 0.8:
        dynamic_gate = min_p - 0.015
    elif vrs > 1.2:
        dynamic_gate = min_p + 0.020
    else:
        dynamic_gate = min_p
        
    dynamic_gate = max(dynamic_gate, 0.65)
        
    if float(norm_p) < float(dynamic_gate):
        return False, f"Point 5 Fail: Blended conviction {norm_p:.3f} < dynamic gate {dynamic_gate:.3f} (Base={min_p:.3f}, VRS={vrs:.2f})"

    # Point 6: Kronos Model Floor
    predicted_dir = direction
    kronos_conf = conviction if predicted_dir == "BUY" else (1.0 - conviction)
    if float(kronos_conf) < 0.70:
        return False, f"Point 6 Fail: Kronos conviction {kronos_conf:.3f} < 0.70 floor"

    # Point 7: XGBoost Model Floor
    xgb_conf = xgb_p if predicted_dir == "BUY" else (1.0 - xgb_p)
    if float(xgb_conf) < 0.65:
        return False, f"Point 7 Fail: XGB conviction {xgb_conf:.3f} < 0.65 floor"

    # Point 8: Divergence Gate
    model_divergence = abs(kronos_conf - xgb_conf)
    div_limit = 0.15 if is_starved == True else 0.30
    if float(model_divergence) > float(div_limit):
        return False, f"Point 8 Fail: Model divergence {model_divergence:.3f} > limit {div_limit:.3f}"

    # Point 9: Regime State Validity
    if hmm_state not in ["BULL", "BEAR", "RANGE"]:
        return False, f"Point 9 Fail: Invalid HMM state {hmm_state}"

    # Point 10: Regime Probability Minimum (Rule 3.3)
    hmm_prob = 1.0
    try:
        from arcticdb import Arctic
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        row = store["oracle_cache"].read(f"{symbol}_hmm").data.iloc[-1]
        hmm_prob = float(row["prob"])
    except:
        pass
    sym_upper = symbol.upper()
    is_index = (any(idx in sym_upper for idx in ["NAS100", "US30", "SP500", "SPX500", "GER40", "US2000", "HK50"]) == True)
    min_regime_prob = 0.65 if is_index == True else 0.60
    if float(hmm_prob) < float(min_regime_prob):
        return False, f"Point 10 Fail: [HARD_VETO] [REGIME_MINIMUM_VETO] HMM regime probability {hmm_prob:.3f} < required {min_regime_prob:.3f}"

    # Point 11: Zero-MFE Prevention (Rule 4.1)
    retries = 5
    momentum_confirmed = False
    tick = mt5.symbol_info_tick(symbol)
    ticks_count = 8 if is_index == True else 5
    if tick is not None:
        for attempt in range(retries):
            ticks = mt5.copy_ticks_from(symbol, datetime.now(), ticks_count, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) >= ticks_count:
                last_val = ticks[-1]['ask'] if direction == "BUY" else ticks[-1]['bid']
                first_val = ticks[0]['ask'] if direction == "BUY" else ticks[0]['bid']
                diff = last_val - first_val
                if (direction == "BUY" and diff > 0) or (direction == "SELL" and diff < 0):
                    momentum_confirmed = True
                    break
            logger.info(f"[{symbol}] Point 11 Check: Zero-MFE failed on attempt {attempt+1}. Soft delaying...")
            time.sleep(0.1)
            
        if momentum_confirmed == False:
            return False, f"Point 11 Fail: [HARD_VETO] [MOMENTUM_VETO] Zero-MFE check failed after {retries} retries."

    # Point 12: Spread-to-ATR Ratio (Rule 4.2)
    if tick is not None:
        current_spread = tick.ask - tick.bid
        if "GER40" in sym_upper or "HK50" in sym_upper:
            spread_atr_limit = 0.025
        elif "US30" in sym_upper or "NAS100" in sym_upper:
            spread_atr_limit = 0.020
        elif "XAUUSD" in sym_upper or "GOLD" in sym_upper:
            spread_atr_limit = 0.015
        else:
            spread_atr_limit = 0.030
            
        spread_atr_ratio = current_spread / (current_atr + 1e-12)
        if float(spread_atr_ratio) > float(spread_atr_limit):
            return False, f"Point 12 Fail: Spread-to-ATR ratio {spread_atr_ratio:.4f} > limit {spread_atr_limit:.4f}"

    # Point 13: Minimum R:R Gate (Rule 4.3)
    distance_to_fractal_sl = calculate_fractal_swing(symbol, direction, lookback=20)
    calculated_sl_dist = max(3.0 * current_atr, distance_to_fractal_sl)
    broker_minimum_sl = info.trade_stops_level * info.point
    final_sl_dist = max(calculated_sl_dist, broker_minimum_sl)
    
    p_entry = conviction if direction == "BUY" else (1.0 - conviction)
    if p_entry < 0.5:
        p_entry = abs(conviction - 0.5) + 0.5
    p_entry = max(p_entry, 0.60)
    normalized_p = (p_entry - 0.60) / 0.40
    tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
    tp_dist = current_atr * tp_multiplier
    
    min_rr = 2.2 if is_index == True else 1.8
    prospective_rr = tp_dist / (final_sl_dist + 1e-12)
    if float(prospective_rr) < float(min_rr):
        return False, f"Point 13 Fail: Prospective R:R {prospective_rr:.2f} < required {min_rr:.2f}"

    # Point 14: JPY pair session open blackout (Rule 6.2)
    jpy_pairs = {"USDJPY", "GBPJPY", "EURJPY", "AUDJPY", "NZDJPY", "CHFJPY", "CADJPY"}
    if sym_upper in jpy_pairs:
        if is_in_jpy_blackout() == True:
            return False, "Point 14 Fail: JPY pair session open blackout"

    # Point 15: JPY pair dP/dt velocity kill switch (Rule 6.2)
    if sym_upper in jpy_pairs:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 2)
        if rates is not None and len(rates) >= 2:
            dp_dt = (rates[-1]['close'] - rates[-2]['close']) / (rates[-2]['close'] + 1e-9) * 100.0
            if float(dp_dt) <= -0.20:
                return False, f"Point 15 Fail: JPY pair dP/dt velocity kill switch active ({dp_dt:.3f}% <= -0.20%)"

    # Point 16: Metals major USD release blackout (Rule 6.3)
    if is_in_metals_macro_blackout(symbol) == True:
        return False, "Point 16 Fail: Metals major USD release blackout"

    # Point 17: Wall 5 Dynamic Tier Blackout
    is_blackout, veto_reason = is_wall5_macro_blackout(symbol)
    if is_blackout == True:
        return False, f"Point 17 Fail: {veto_reason}"

    # Point 18: Account Daily Drawdown (Rule 7.1)
    if float(get_daily_drawdown()) >= 0.03:
        return False, "Point 18 Fail: Daily drawdown >= 3.0% (FORTRESS_MODE active)"

    # Point 19: Consecutive Losses SRE Hard Pause (Rule 7.2)
    is_paused, time_left = is_consec_losses_paused()
    if is_paused == True:
        return False, f"Point 19 Fail: SRE Hard Pause active due to consecutive losses ({time_left:.1f}s remaining)"

    # Point 20: Index Minimum Equity Floor (Rule 7.3)
    if is_index == True and float(acc.equity) < 2000.0:
        return False, f"Point 20 Fail: Equity ${acc.equity:.2f} < $2000 floor for indices"

    # Sandbox Fuzzing Block: Safely reject fuzzer signals to prevent real execution
    is_fuzzing = payload.get("is_fuzzing", False) if payload else False
    if is_fuzzing:
        return False, "Fuzzing signal sandbox block"

    logger.info(f"[{symbol}] 20-point Composite Pre-Flight Checklist PASSED successfully!")
    return True, "Passed"

def is_weekend_blackout(symbol):
    crypto_keywords = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK", "AVAX"]
    if any(k in symbol.upper() for k in crypto_keywords):
        return False
    tick = mt5.symbol_info_tick("EURUSD")
    if not tick: return False
    dt = datetime.fromtimestamp(tick.time, tz=timezone.utc)
    if (dt.weekday() == 4 and dt.strftime('%H:%M') >= "23:55") or (dt.weekday() in [5, 6]) or (dt.weekday() == 0 and dt.strftime('%H:%M') < "00:15"):
        return True
    return False

def has_active_position(symbol):
    # v23.9 Pure Validation: Use substring match on all positions to handle broker suffixes
    # CRITICAL: No execution side-effects permitted in state validation.
    all_positions = mt5.positions_get()
    if all_positions:
        for p in all_positions:
            if symbol in p.symbol and p.magic == MAGIC_NUMBER:
                return True
    return False

def calculate_micro_price(bid: float, ask: float, bid_vol: float, ask_vol: float) -> float:
    """Oxford Micro-Price (v23.1). Volume-weighted mid-price."""
    total_vol = bid_vol + ask_vol
    if total_vol <= 0: return (bid + ask) / 2.0
    return (bid * ask_vol + ask * bid_vol) / total_vol

def calculate_kelly_lot(symbol, conviction):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    acc = mt5.account_info()
    if not info or not tick or not acc: return 0.0

    # ── v23.1: Micro-Price Baseline ──
    bid_vol = getattr(tick, 'bid_volume', 0.0)
    ask_vol = getattr(tick, 'ask_volume', 0.0)
    micro_price = calculate_micro_price(tick.bid, tick.ask, bid_vol, ask_vol)
    
    p = abs(conviction - 0.5) + 0.5
    q = 1.0 - p
    f_star = p - (q / 1.5)
    f_final = min(max(0, f_star * KELLY_FRACTION), HARD_RISK_CAP) 
    risk_usd = acc.equity * f_final
    
    # ── v25.0: Align Sizing SL with Execution SL (ATR/Swing) ──
    direction = "BUY" if conviction > 0.5 else "SELL"
    current_atr, _ = calculate_atr_and_swing(symbol, direction, lookback=20)
    distance_to_fractal_sl = calculate_fractal_swing(symbol, direction, lookback=20)
    spread = tick.ask - tick.bid
    spread_buffer = spread * 1.5
    sl_dist_price = max(3.0 * current_atr, distance_to_fractal_sl)
    
    # Fallback if ATR is 0
    if sl_dist_price <= 0:
        sl_dist_price = (micro_price * 0.005) + spread_buffer # Default 0.5%
        
    # ── v26.1: ATR-Adjusted Position Sizing ──
    sl_dist_points = sl_dist_price / (info.point + 1e-12)
    point_val = info.trade_tick_value / (info.trade_tick_size / info.point)
    
    # Kelly-suggested lot
    raw_kelly_vol = risk_usd / (sl_dist_points * point_val + 1e-12)
    kelly_lot = math.floor(raw_kelly_vol / info.volume_step) * info.volume_step
    
    # ATR-Adjusted lot
    max_dollar_risk = acc.balance * 0.02
    atr_raw_vol = max_dollar_risk / (sl_dist_points * point_val + 1e-12)
    atr_adjusted_lot = math.floor(atr_raw_vol / info.volume_step) * info.volume_step
    
    lot = min(kelly_lot, atr_adjusted_lot)
    
    # Directive 2: Target Volatility position sizing scaling
    try:
        from agents.risk_agent import calculate_volatility_scalar
        vol_scalar = calculate_volatility_scalar(symbol, current_atr)
        scaled_lot = lot * vol_scalar
        # Align with volume_step
        scaled_lot = math.floor(scaled_lot / info.volume_step) * info.volume_step
        logger.info(
            f"[{symbol}] [TARGET_VOL_SCALING] vol_scalar={vol_scalar:.4f} (current_ATR={current_atr:.5f}) | "
            f"Lot scaled: {lot:.2f} -> {scaled_lot:.2f}"
        )
        lot = scaled_lot
    except Exception as e:
        logger.warning(f"[{symbol}] Target Volatility scaling failed: {e}")
        
    logger.info(f"[{symbol}] DEBUG LOT: Balance={acc.balance:.2f} | MaxRisk=${max_dollar_risk:.2f} | KellyLot={kelly_lot} | AtrLot={atr_adjusted_lot} | FinalLot={lot}")

    # Directive Omega: Rule 1.1 - Small Account Floor Sizing Veto
    if lot < info.volume_min:
        logger.warning(f"[{symbol}] ZERO_SIZING_VETO: Calculated lot size {lot:.4f} < broker min {info.volume_min}. Abolishing small account floor; returning 0.0.")
        return 0.0
        
    lot = max(min(lot, info.volume_max), 0.0) 
    return lot


def calculate_ac_trajectory(
    total_size: float,
    risk_aversion: float = 0.1,
    volatility: float = 0.0001,
    n_slices: int = 5,
    impact_params: Optional[Dict] = None,
) -> List[float]:
    if n_slices <= 1:
        return [total_size]

    params = impact_params or {}
    eta    = params.get("eta", 0.01)
    sigma  = params.get("sigma", volatility) or volatility

    eta_tilde = eta * (n_slices / max(1.0, total_size))
    kappa_sq  = (risk_aversion * (sigma ** 2)) / (eta_tilde + 1e-9)
    kappa     = np.sqrt(kappa_sq)

    T = float(n_slices)
    time_steps = [k * (T / n_slices) for k in range(n_slices + 1)]
    
    x_traj = [total_size * np.sinh(kappa * (T - t)) / (np.sinh(kappa * T) + 1e-9) for t in time_steps]
    child_sizes = [x_traj[k] - x_traj[k + 1] for k in range(n_slices)]
    
    return [max(0.0, float(s)) for s in child_sizes]

def calculate_atr_and_swing(symbol: str, direction: str, lookback: int = 20) -> Tuple[float, float]:
    """Calculates live macroscopic ATR (H1) and distance to recent Swing High/Low."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, lookback + 1)
    if rates is None or len(rates) < lookback + 1:
        tick = mt5.symbol_info_tick(symbol)
        spread = (tick.ask - tick.bid) if tick else 0.0001
        est_atr = spread * 3.0
        return est_atr, est_atr * 2.0
    
    high = rates['high']
    low = rates['low']
    close = rates['close']
    
    tr = np.zeros(lookback)
    for i in range(lookback):
        h_l = high[i+1] - low[i+1]
        h_pc = abs(high[i+1] - close[i])
        l_pc = abs(low[i+1] - close[i])
        tr[i] = max(h_l, h_pc, l_pc)
    current_atr = float(np.mean(tr))
    
    tick = mt5.symbol_info_tick(symbol)
    current_price = tick.ask if direction == "BUY" else tick.bid
    
    if direction == "BUY":
        swing_low = float(np.min(low))
        distance_to_swing = max(0.0, current_price - swing_low)
    else:
        swing_high = float(np.max(high))
        distance_to_swing = max(0.0, swing_high - current_price)
        
    return current_atr, distance_to_swing

def calculate_fractal_swing(symbol: str, direction: str, lookback: int = 20) -> float:
    """v26.6: Rigid Fractal Anchoring (The 20-Bar Rule) using H4 data."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, lookback)
    tick = mt5.symbol_info_tick(symbol)
    
    if rates is None or len(rates) == 0 or tick is None:
        # Fallback if H4 data is missing
        return 0.0
        
    current_spread = abs(tick.ask - tick.bid)
    spread_safety = current_spread * 1.5
    
    if direction == "BUY":
        # Find absolute MIN(Low)
        fractal_low = float(np.min(rates['low']))
        fractal_sl = fractal_low - spread_safety
        # Calculate distance
        distance = max(0.0, tick.ask - fractal_sl)
        return distance
    else:
        # Find absolute MAX(High)
        fractal_high = float(np.max(rates['high']))
        fractal_sl = fractal_high + spread_safety
        # Calculate distance
        distance = max(0.0, fractal_sl - tick.bid)
        return distance

def verify_execution_signature(ticket: int):
    """
    Directive 4: Post-Execution Signature Audit.
    Assures that the deal comment contains the active AGENT_SIGNATURE.
    If not, flags an identity breach and writes the emergency shutdown flag.
    """
    logger.info(f"[POST-EXEC AUDIT] Verification signature for ticket #{ticket}...")
    import MetaTrader5 as mt5
    # Query MT5 history for the deal/order ticket
    deals = mt5.history_deals_get(ticket=ticket)
    if not deals:
        deals = mt5.history_deals_get(position=ticket)
        
    if deals:
        deal = deals[-1]
        comment = deal.comment or ""
        logger.info(f"[POST-EXEC AUDIT] Found deal #{deal.ticket} with comment '{comment}'")
        
        # Check signature breach (allowing version prefix fallback to handle severe broker-side truncation)
        from sentinel.version_manifest import SENTINEL_VERSION
        if AGENT_SIGNATURE not in comment and f"SENTINEL_{SENTINEL_VERSION}" not in comment:
            logger.critical(f"[IDENTITY BREACH] Rogue execution detected! Deal comment '{comment}' does not match active '{AGENT_SIGNATURE}'!")
            
            # Write the emergency shutdown flag
            flag_path = r"C:\Sentinel_Project\IDENTITY_BREACH.flag"
            with open(flag_path, "w", encoding="utf-8") as flag_file:
                flag_file.write(
                    f"IDENTITY BREACH: Ticket #{ticket} was executed with legacy/rogue comment '{comment}'.\n"
                    f"Expected active signature: '{AGENT_SIGNATURE}'.\n"
                    f"Time of breach: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
            
            logger.critical(f"[IDENTITY BREACH] Emergency boot block file written: {flag_path}")
            sys.exit(1)
        else:
            logger.info(f"[POST-EXEC AUDIT] Signature verified successfully for ticket #{ticket}")
    else:
        logger.warning(f"[POST-EXEC AUDIT] No matching deal found for ticket #{ticket} to audit signature.")

def get_timesfm_sl_distance(symbol, direction, entry_price, current_atr):
    timesfm_valid = False
    p10 = None
    p90 = None
    try:
        from arcticdb import Arctic
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        if store.has_library("oracle_cache"):
            lib = store["oracle_cache"]
            key = f"{symbol}_timesfm"
            if lib.has_symbol(key):
                item = lib.read(key)
                if item is not None and not item.data.empty:
                    data = item.data.iloc[-1]
                    p10_val = float(data["p10"])
                    p90_val = float(data["p90"])
                    timestamp_val = float(data["timestamp"])
                    
                    # Stale Check: older than 4 hours (14400 seconds)
                    from datetime import datetime, timezone
                    import time
                    current_time = datetime.now(timezone.utc).timestamp()
                    age = current_time - timestamp_val
                    if age <= 14400:
                        # Boundary Breach Check
                        if direction == "BUY" and entry_price >= p10_val:
                            timesfm_valid = True
                            p10 = p10_val
                            p90 = p90_val
                        elif direction == "SELL" and entry_price <= p90_val:
                            timesfm_valid = True
                            p10 = p10_val
                            p90 = p90_val
                        else:
                            logger.warning(f"[{symbol}] TimesFM Boundary Breach Check FAILED: entry_price={entry_price:.5f}, p10={p10_val:.5f}, p90={p90_val:.5f}")
                    else:
                        logger.warning(f"[{symbol}] TimesFM Cache Stale: age={age:.1f}s > 14400s")
    except Exception as e:
        logger.warning(f"[{symbol}] Failed to retrieve/validate TimesFM boundaries: {e}")

    if timesfm_valid:
        dist = (entry_price - p10) if direction == "BUY" else (p90 - entry_price)
        logger.info(f"[{symbol}] TimesFM SL active: distance={dist:.5f}")
        return dist, True
    else:
        dist = 3.0 * current_atr
        logger.warning(f"[{symbol}] Coherence Protection Engaged: Fallback ATR SL active: distance={dist:.5f}")
        return dist, False

def perform_mt5_trade(symbol, direction, lot, conviction, vpin=0.0, alpha_features=None):
    if alpha_features is None:
        alpha_features = {'P': conviction, 'vpin': vpin}
    assert len(alpha_features) > 0, "alpha_features must be populated"
    
    # Extract timeframe from alpha_features, default to 'H4'
    entry_tf = "H4"
    if alpha_features and isinstance(alpha_features, dict):
        entry_tf = alpha_features.get("timeframe", alpha_features.get("tf", "H4"))
    
    strategy_type = alpha_features.get("strategy_type", "MOMENTUM") if alpha_features else "MOMENTUM"
    strategy_code = "MR" if strategy_type == "MEAN_REVERSION" else "MO"
    from sentinel.version_manifest import SENTINEL_VERSION
    prefix = f"SENTINEL_{SENTINEL_VERSION}_{strategy_code}"
    deal_comment = f"{prefix}_TF{entry_tf}_P{conviction:.2f}"[:31]
    
    try:
        # Extract model scores from alpha_features for the checklist
        xgb_p = alpha_features.get("xgb_p", 0.5) if alpha_features else 0.5
        ddqn_p = alpha_features.get("ddqn_p", 0.5) if alpha_features else 0.5
        hmm_state = alpha_features.get("regime", "RANGE") if alpha_features else "RANGE"
        
        passed, reason = run_composite_preflight_checklist(
            symbol, direction, lot, conviction, vpin, hmm_state, xgb_p, ddqn_p, alpha_features
        )
        if not passed:
            is_fuzzing = alpha_features.get("is_fuzzing", False) if alpha_features else False
            if is_fuzzing:
                logger.info(f"[{symbol}] [SRE_FUZZ_TEST_PASSED] Fuzzing signal rejected as expected. Reason: {reason}")
            else:
                logger.warning(f"[{symbol}] COMPOSITE_PREFLIGHT_VETO: Trade rejected. Reason: {reason}")
            raise HTTPException(status_code=403, detail=f"COMPOSITE_PREFLIGHT_VETO: {reason}")

        tick = mt5.symbol_info_tick(symbol)
        if not tick: 
            logger.error(f"[{symbol}] Failed to get tick for execution.")
            return False
        
        # v23.1 Micro-Price Audit Trail
        bid_vol = getattr(tick, 'bid_volume', 0.0)
        ask_vol = getattr(tick, 'ask_volume', 0.0)
        micro_price = calculate_micro_price(tick.bid, tick.ask, bid_vol, ask_vol)
        logger.info(f"[{symbol}] Execution Baseline: Micro-Price={micro_price:.5f} | Mid-Price={(tick.bid+tick.ask)/2:.5f}")

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        info = mt5.symbol_info(symbol)
        digits = info.digits if info else 5
        price = round(tick.ask if direction == "BUY" else tick.bid, digits)

        # Directive 1: CADES Conviction-Scaled TP & Structural SL (v23.14 Architecture)
        current_atr, _ = calculate_atr_and_swing(symbol, direction, lookback=20)
        
        # Directive 3: TimesFM Coherence Protection
        tfm_dist, tfm_valid = get_timesfm_sl_distance(symbol, direction, price, current_atr)
        calculated_sl_dist = tfm_dist
        
        broker_minimum_sl = info.trade_stops_level * info.point if info else 0.0001
        final_sl_dist = max(calculated_sl_dist, broker_minimum_sl)
        
        logger.info(f"[{symbol}] CADES SL Validation: ATR={current_atr:.5f} | TimesFM_Valid={tfm_valid} | FinalSL={final_sl_dist:.5f}")
        
        sl_price = price - final_sl_dist if direction == "BUY" else price + final_sl_dist
        sl_price = round(sl_price, digits)

        # Directive 1: Ensure Conviction score (P) is correctly extracted. Default to 0.80 if missing.
        conv_val = conviction if conviction is not None and conviction > 0 else 0.80
        # If conviction is already absolute directional confidence, use directly, otherwise normalize
        p_entry = conv_val if direction == "BUY" else (1.0 - conv_val)
        if p_entry < 0.5:
            p_entry = abs(conv_val - 0.5) + 0.5
        p_entry = max(p_entry, 0.60)
        
        # Directive 1: Implement Logarithmic TP Squashing (SRE Optimization)
        # Linear: tp_dist = current_atr * (2.0 + 4.0 * ((p_entry - 0.60) / 0.40))
        normalized_p = (p_entry - 0.60) / 0.40
        tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
        tp_dist = current_atr * tp_multiplier
        
        # Directional Math: BUY = entry + tp_dist, SELL = entry - tp_dist
        tp_price = price + tp_dist if direction == "BUY" else price - tp_dist
        tp_price = round(tp_price, digits)
        
        logger.info(f"[{symbol}] CADES TP Scaled: P={p_entry:.4f} -> TP Dist={tp_dist/current_atr:.2f}x ATR")

        # ── v23.0: Almgren-Chriss Trajectory Gate ─────────────────────────────────
        if lot >= AC_LARGE_ORDER_THRESHOLD:
            atr_proxy = (info.trade_contract_size * info.point * 100) if info else 0.0001
            trajectory = calculate_ac_trajectory(
                total_size=lot,
                risk_aversion=0.1,
                volatility=atr_proxy,
                n_slices=5,
            )
            # Apply strict broker volume step floor to prevent 10014 Invalid Volume rejections
            valid_slices = []
            vol_step = info.volume_step if info else 0.01
            for child_lot in trajectory:
                r_lot = round(child_lot / vol_step) * vol_step
                if r_lot >= vol_step:
                    valid_slices.append(r_lot)
                elif valid_slices:
                    valid_slices[-1] += r_lot
                    valid_slices[-1] = round(valid_slices[-1] / vol_step) * vol_step
            
            logger.info(
                f"[AC_EXECUTION] {symbol} LARGE ORDER {lot} lots -> slicing into "
                f"{len(valid_slices)} valid child orders: {valid_slices}"
            )
            success = True
            for i, child_lot_rounded in enumerate(valid_slices):
                child_request = {
                    "action":       mt5.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       float(child_lot_rounded),
                    "type":         order_type,
                    "price":        price,
                    "sl":           0.0,
                    "tp":           0.0,
                    "magic":        MAGIC_NUMBER,
                    "comment":      f"SENTINEL_AC_{i+1}of{len(valid_slices)}_P{conviction:.2f}"[:29],
                    "type_time":    mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(child_request)
                if res is None:
                    logger.error(f"[AC] Child order {i+1} FAILED (API None)")
                    success = False
                else:
                    logger.info(f"[{symbol}] [AC_{i+1}] Broker Response: Retcode={res.retcode} | Comment={res.comment}")
                    if res.retcode == mt5.TRADE_RETCODE_DONE:
                        ticket = getattr(res, 'order', getattr(res, 'deal', 0))
                        logger.info(f"[AC] Child order {i+1}/{len(valid_slices)} filled ticket #{ticket}. Attaching SL/TP via ECN-Safe modification...")
                        verify_execution_signature(ticket)
                        positions = mt5.positions_get(ticket=ticket)
                        if positions:
                            pos = positions[0]
                            alpha_features = {'P': conviction, 'atr': current_atr, 'vpin': vpin}
                            info = mt5.symbol_info(pos.symbol)
                            if info:
                                # Directive 1: Implement the Dynamic ATR Floor (v25.0)
                                raw_atr = current_atr
                                # Fallback to 0.25% of the open price if raw_atr is dangerously small
                                price_based_min = pos.price_open * 0.0025 
                                # Check against the broker's legally required minimum stop level
                                broker_min = info.trade_stops_level * info.point
                                
                                # Directive 2: SRE Hardened Safety Floor (v26.1)
                                # Even if broker_min is 0, we enforce a minimum of 1.5x ATR
                                # NEW: Spread-Aware Floor - ensure SL/TP is at least 1.0x Spread + 1.2x ATR
                                tick = mt5.symbol_info_tick(pos.symbol)
                                current_spread = abs(tick.ask - tick.bid) if tick else 0.0
                                spread_safety = current_spread * 1.5 
                                
                                sre_safety_floor = max(1.5 * raw_atr, spread_safety)
                                
                                # The True ATR is the largest of these
                                true_atr = max(raw_atr, price_based_min, broker_min, sre_safety_floor)
                                
                                # v24.0 Directive 1: Avellaneda-Stoikov Inventory Skewing
                                active_sym_positions = mt5.positions_get(symbol=pos.symbol) or []
                                current_position_size = sum(p.volume for p in active_sym_positions if (p.type == mt5.ORDER_TYPE_BUY if direction == "BUY" else p.type == mt5.ORDER_TYPE_SELL) and p.magic == MAGIC_NUMBER)
                                
                                grid_expansion_scalar = 1.0 + 0.25 * (current_position_size ** 1.2)
                                tp_skew_scalar = max(0.40, 1.0 - 0.10 * current_position_size)

                                # Directive 3: TimesFM Coherence Protection
                                tfm_dist, tfm_valid = get_timesfm_sl_distance(pos.symbol, direction, pos.price_open, true_atr)
                                sl_dist = tfm_dist * grid_expansion_scalar
                                # Secure TP Calculation
                                try:
                                    p_val = float(alpha_features.get('P', conviction))
                                except (ValueError, TypeError):
                                    p_val = 0.80

                                # Directive 1: Implement Logarithmic TP Squashing (SRE Optimization)
                                normalized_p_val = (max(p_val, 0.60) - 0.60) / 0.40
                                tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p_val)
                                tp_dist = tp_multiplier * true_atr * tp_skew_scalar # Tighten TP bounds incrementally
                                
                                # Assume active_regime is passed in the alpha_features payload
                                active_regime = alpha_features.get('regime')
                                if not active_regime:
                                    try:
                                        from arcticdb import Arctic
                                        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
                                        row = store["oracle_cache"].read(f"{pos.symbol}_meta").data.iloc[-1]
                                        active_regime = str(row["hmm_state"]).upper()
                                    except Exception:
                                        active_regime = "TRENDING"
                                else:
                                    active_regime = str(active_regime).upper()

                                if active_regime == "RANGE":
                                    # v27.0: 1.5x floor to ensure TP clears the spread in mean-reverting chop.
                                    tp_dist = max(tp_dist * 0.45, true_atr * 0.8)
                                elif active_regime == "HIGH_VOLATILITY":
                                    # Widen slightly to avoid noise
                                    tp_dist = tp_dist * 1.2

                                # 2. Directional Math (CRITICAL)
                                if pos.type == mt5.ORDER_TYPE_BUY:
                                    new_sl = pos.price_open - sl_dist
                                    new_tp = pos.price_open + tp_dist
                                elif pos.type == mt5.ORDER_TYPE_SELL:
                                    new_sl = pos.price_open + sl_dist
                                    new_tp = pos.price_open - tp_dist
                                else:
                                    new_sl = sl_price
                                    new_tp = tp_price
                                
                                # 3. Universal Tick Size Normalization
                                tick_size = info.trade_tick_size
                                if tick_size > 0:
                                    new_tp = round(new_tp / tick_size) * tick_size
                                    if new_sl > 0:
                                        new_sl = round(new_sl / tick_size) * tick_size

                                new_sl = round(new_sl, info.digits) if new_sl > 0 else 0.0
                                new_tp = round(new_tp, info.digits)
                                
                                # v27.0: Level 42 SRE Atomic Modification
                                atomic_sl_tp_modification(pos, new_sl, new_tp)
                    else:
                        logger.error(f"[AC] Child order {i+1} REJECTED: Retcode={res.retcode} | Comment={res.comment}")
                        success = False
                time.sleep(0.05)
            return success

        # Directive 3: Passive Maker Routing for High Toxicity
        # Conditions: P > 0.85 AND H_int > 0.00005
        # Fetch Hawkes Intensity from ArcticDB cache
        hawkes_intensity = 0.0
        try:
            from arcticdb import Arctic
            store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
            row = store["oracle_cache"].read(f"{symbol}_meta").data.iloc[-1]
            hawkes_intensity = float(row.get("hawkes_intensity", 0.0))
        except Exception:
            pass

        if conv_val > 0.85 and hawkes_intensity > 0.00005:
            logger.info(f"[{symbol}] High Toxicity detected (H_int={hawkes_intensity:.6f}). Switching to PASSIVE MAKER routing at Micro-Price.")
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
            
            # Directive 1: Entry Price Normalization
            tick_size = info.trade_tick_size
            if tick_size > 0:
                price = round(micro_price / tick_size) * tick_size
            else:
                price = round(micro_price, digits)
            price = round(price, digits)
            
            time_type = mt5.ORDER_TIME_SPECIFIED
            expiration = int(time.time() + 5)
        else:
            time_type = mt5.ORDER_TIME_GTC
            expiration = 0

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(lot),
            "type":         order_type,
            "price":        price,
            "sl":           0.0,
            "tp":           0.0,
            "magic":        MAGIC_NUMBER,
            "comment":      deal_comment,
            "type_time":    time_type,
            "expiration":   expiration,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        
        # Directive 2: The Limit-to-Market Fallback
        if res and res.retcode in [mt5.TRADE_RETCODE_INVALID_PRICE, mt5.TRADE_RETCODE_INVALID_STOPS] and \
           order_type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
            
            logger.warning(f"[{symbol}] [MAKER REJECTED] Retcode {res.retcode}. Price drifted or invalid. Falling back to Market Taker execution to secure alpha.")
            
            # Downgrade to Market Order
            order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
            tick = mt5.symbol_info_tick(symbol)
            price = tick.ask if direction == "BUY" else tick.bid
            price = round(price, digits)
            
            request["type"] = order_type
            request["price"] = price
            request["type_time"] = mt5.ORDER_TIME_GTC
            request["expiration"] = 0
            request["comment"] = f"{prefix}_TF{entry_tf}_P{conviction:.2f}"[:31]
            
            res = mt5.order_send(request)

        if res is None:
            err = mt5.last_error()
            logger.critical(f"[FAIL] [CRITICAL_API_ERROR] {symbol} {direction} | mt5.order_send returned None. Last error: {err}")
            return False

        logger.info(f"[{symbol}] Broker Response: Retcode={res.retcode} | Comment={res.comment}")
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            ticket = getattr(res, 'order', getattr(res, 'deal', 0))
            logger.info(f"[OK] [EXECUTED] {symbol} {direction} {lot} lots at {price} filled ticket #{ticket}. Attaching SL/TP via ECN-Safe modification...")
            verify_execution_signature(ticket)

            # v27.0: Post-Execution Verification — confirm broker comment matches AGENT_SIGNATURE
            deals = mt5.history_deals_get(ticket=ticket)
            if deals:
                deal = deals[0]
                deal_comment = deal.comment or ""
                if AGENT_SIGNATURE not in deal_comment:
                    logger.warning(f"[POST-EXEC VERIFY] Deal #{ticket} comment mismatch: expected '{AGENT_SIGNATURE}', got '{deal_comment}'.")
                else:
                    logger.info(f"[POST-EXEC VERIFY] Deal #{ticket} comment verified: '{deal_comment}'")
                    
            positions = mt5.positions_get(ticket=ticket)
            if positions:
                pos = positions[0]
                if AGENT_SIGNATURE not in (pos.comment or ""):
                    logger.warning(f"[POST-EXEC VERIFY] Ticket #{ticket} comment mismatch: expected '{AGENT_SIGNATURE}', got '{pos.comment}'. Possible broker truncation or injection.")
                else:
                    logger.info(f"[POST-EXEC VERIFY] Ticket #{ticket} comment verified: '{pos.comment}'")
                alpha_features = {'P': conviction, 'atr': current_atr, 'vpin': vpin}
                info = mt5.symbol_info(pos.symbol)
                if info:
                    # Directive 1: Implement the Dynamic ATR Floor
                    raw_atr = float(alpha_features.get('atr', current_atr))
                    # Fallback to 0.25% of the open price if raw_atr is dangerously small
                    price_based_min = pos.price_open * 0.0025 
                    # Check against the broker's legally required minimum stop level
                    broker_min = info.trade_stops_level * info.point
                    
                    # Directive 2: SRE Hardened Safety Floor (v26.1)
                    # NEW: Spread-Aware Floor
                    tick = mt5.symbol_info_tick(pos.symbol)
                    current_spread = abs(tick.ask - tick.bid) if tick else 0.0
                    spread_safety = current_spread * 1.5
                    
                    sre_safety_floor = max(1.5 * raw_atr, spread_safety)
                    
                    # The True ATR is the largest of these
                    true_atr = max(raw_atr, price_based_min, broker_min, sre_safety_floor)
                    
                    # v24.0 Directive 1: Avellaneda-Stoikov Inventory Skewing
                    active_sym_positions = mt5.positions_get(symbol=pos.symbol) or []
                    current_position_size = sum(p.volume for p in active_sym_positions if (p.type == mt5.ORDER_TYPE_BUY if direction == "BUY" else p.type == mt5.ORDER_TYPE_SELL) and p.magic == MAGIC_NUMBER)
                    
                    grid_expansion_scalar = 1.0 + 0.25 * (current_position_size ** 1.2)
                    tp_skew_scalar = max(0.40, 1.0 - 0.10 * current_position_size)

                    # Directive 3: TimesFM Coherence Protection
                    tfm_dist, tfm_valid = get_timesfm_sl_distance(pos.symbol, direction, pos.price_open, true_atr)
                    sl_dist = tfm_dist * grid_expansion_scalar
                    # Secure TP Calculation
                    try:
                        p_val = float(alpha_features.get('P', conviction))
                    except (ValueError, TypeError):
                        p_val = 0.80

                    # Directive 1: Implement Logarithmic TP Squashing (SRE Optimization)
                    normalized_p_val = (max(p_val, 0.60) - 0.60) / 0.40
                    tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p_val)
                    tp_dist = tp_multiplier * true_atr * tp_skew_scalar # Tighten TP bounds incrementally
                    
                    # Assume active_regime is passed in the alpha_features payload
                    active_regime = alpha_features.get('regime')
                    if not active_regime:
                        try:
                            from arcticdb import Arctic
                            store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
                            row = store["oracle_cache"].read(f"{pos.symbol}_meta").data.iloc[-1]
                            active_regime = str(row["hmm_state"]).upper()
                        except Exception:
                            active_regime = "TRENDING"
                    else:
                        active_regime = str(active_regime).upper()

                    if active_regime == "RANGE":
                        # v27.0: Updated to mathematically safe calculation
                        tp_dist = max(tp_dist * 0.45, true_atr * 0.8)
                    elif active_regime == "HIGH_VOLATILITY":
                        # Widen slightly to avoid noise
                        tp_dist = tp_dist * 1.2

                    # 2. Directional Math (CRITICAL)
                    is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
                    
                    if is_buy:
                        target_sl = pos.price_open - sl_dist
                        target_tp = pos.price_open + tp_dist
                    else: # SELL
                        target_sl = pos.price_open + sl_dist
                        target_tp = pos.price_open - tp_dist
                    
                    # 3. Universal v25.1 Armor Normalization
                    tick = mt5.symbol_info_tick(pos.symbol)
                    curr_price = tick.bid if is_buy else tick.ask # SL checked against opposite side
                    
                    new_sl = enforce_stoplevel_and_normalize(pos.symbol, curr_price, target_sl, is_sl=True, is_buy=is_buy)
                    new_tp = enforce_stoplevel_and_normalize(pos.symbol, curr_price, target_tp, is_sl=False, is_buy=is_buy)
                    
                    # v27.0: Level 42 SRE Atomic Modification
                    atomic_sl_tp_modification(pos, new_sl, new_tp)
            return True
        else:
            # Directive 1: Strict Retcode Logging (v23.6 Execution Autopsy)
            logger.critical(f"[FAIL] [BROKER_REJECTION] {symbol} {direction} | Retcode: {res.retcode} | Comment: {res.comment}")
            return False
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.critical(f"[FATAL_EXECUTION_CRASH] {symbol} {direction} | Error: {e}\n{traceback.format_exc()}")
        return False

def execute_exit(ticket, symbol, reason):
    try:
        positions = mt5.positions_get(ticket=ticket)
        if not positions: return False
        pos = positions[0]
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return False
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "magic": MAGIC_NUMBER,
            "comment": f"EXIT_{reason[:15]}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res is None:
            err = mt5.last_error()
            logger.critical(f"[FAIL] [EXIT_FAILED] {symbol} Ticket {ticket} | mt5.order_send returned None. Last error: {err}")
            return False

        if res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[OK] [EXITED] {symbol} Ticket {ticket} Reason: {reason}")
            return True
        
        # Directive 2: Graceful 10013 Error Handling (Idempotency)
        if res.retcode == 10013:
            # Check if the position exists
            if mt5.positions_get(ticket=ticket) is None:
                logger.info(f"[SUCCESS/IDEMPOTENT] Ticket {ticket} already closed by prior process (MT5 10013).")
                return True

        logger.error(f"[FAIL] [EXIT_FAILED] {symbol} Ticket {ticket} Error: {res.retcode} - {res.comment}")
        return False
    except Exception as e:
        import traceback
        logger.critical(f"[FATAL_EXIT_CRASH] {symbol} Ticket {ticket} | Error: {e}\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    # Standard run on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ═══════════════════════════════════════════════════════════════════════════════
# DIRECTIVE 3: AVELLANEDA-STOIKOV MARKET MAKING (v23.1)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_micro_price(bid: float, ask: float, bid_vol: float, ask_vol: float) -> float:
    """
    Oxford Micro-Price (v23.1).
    Volume-weighted mid-price to prevent adverse selection.
    """
    total_vol = bid_vol + ask_vol
    if total_vol <= 0:
        return (bid + ask) / 2.0
    return (bid * ask_vol + ask * bid_vol) / total_vol

def calculate_as_quotes(
    micro_price: float,
    inventory: float,
    volatility: float,
    risk_aversion: float = 0.1,
    time_remaining: float = 1.0,
    spread_factor: float = 1.0,
) -> Tuple[float, float]:
    """
    Avellaneda-Stoikov Optimal Market Making Quotes (v23.1 Oxford Apex).

    Computes the optimal bid and ask limit order prices for a market maker
    who must manage inventory risk while capturing the spread.

    v23.1 Upgrade: Anchored to Micro-Price to account for order book imbalance.

    The AS model provides two key formulas:

    1. Reservation Price (indifference price, inventory-adjusted):
       r = S - q * gamma * sigma^2 * T
       Where:
         S     = current MICRO-PRICE (volume-weighted)
         q     = current inventory (signed: +long, -short)
         gamma = risk aversion parameter
         sigma = volatility (e.g., ATR proxy)
         T     = time remaining in the trading session (normalized [0,1])

    2. Optimal Spread:
       delta = gamma * sigma^2 * T + (2/gamma) * ln(1 + gamma/kappa)
       Simplified here as: delta = gamma * sigma^2 * T + spread_factor

    Args:
        micro_price:    Current volume-weighted Micro-Price (S).
        inventory:      Current signed inventory in lots (+long, -short).
        volatility:     Price volatility proxy (e.g., ATR). Units: price.
        risk_aversion:  Gamma parameter [0.01, 1.0]. Higher = tighter quotes.
        time_remaining: Normalized time in session [0, 1]. Lower = more urgent.
        spread_factor:  Minimum half-spread (e.g., 1.5x bid-ask spread).

    Returns:
        Tuple (bid_price, ask_price) — the optimal limit order prices.
    """
    # Reservation price: skew Micro-Price away from inventory direction
    reservation_price = micro_price - inventory * risk_aversion * (volatility ** 2) * time_remaining

    # Optimal half-spread
    half_spread = 0.5 * (risk_aversion * (volatility ** 2) * time_remaining + spread_factor)
    half_spread = max(half_spread, spread_factor)  # Floor at minimum spread

    bid = reservation_price - half_spread
    ask = reservation_price + half_spread

    logger.info(
        f"[AS_QUOTES] MicroPrice={micro_price:.5f} | Inventory={inventory:.2f} lots "
        f"| Reservation={reservation_price:.5f} | Bid={bid:.5f} | Ask={ask:.5f} "
        f"| HalfSpread={half_spread:.5f}"
    )
    return bid, ask


# ═══════════════════════════════════════════════════════════════════════════════
# DIRECTIVE 4: ALMGREN-CHRISS OPTIMAL EXECUTION SLICING (v23.0)
# ═══════════════════════════════════════════════════════════════════════════════

# Threshold above which AC slicing is mandatory (in lots)
AC_LARGE_ORDER_THRESHOLD = float(os.getenv("AC_LARGE_ORDER_THRESHOLD", "10.0"))

