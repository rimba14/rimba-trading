"""
fastapi_sniper.py - Adaptive Sentinel Direct HTTP Execution Bridge (Machine B)
Ultra-Low-Latency, WebSocket-Free MT5 Execution Node (v24.2 Ironclad CADES)
Concurrency: Idempotent Execution & Mutex Locking Active.
v24.2: Upgraded baseline to Volume-Weighted Micro-Price & Regime-Aware Squashing.
"""

import os
import json
import math
import time
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import uvicorn
import MetaTrader5 as mt5
from dotenv import load_dotenv
import requests
import numpy as np

risk_session = requests.Session()
# Load constitution/config
sys.path.append(r"C:\Sentinel_Project")
from sentinel_config import (
    WATCHLIST, KELLY_FRACTION, PORTFOLIO_HEAT_CAP, 
    LEVERAGE_WALL, STALENESS_THRESHOLD, EPISTEMIC_GATE, 
    MAGIC_NUMBER, HARD_RISK_CAP, AC_LARGE_ORDER_THRESHOLD
)

load_dotenv()

# Configure Logging
LOG_FILE = r"C:\sentinel_logs\fastapi_sniper_v2.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [HTTP_SNIPER] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("HttpSniper")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # Avoid duplicate handlers if the file is re-imported
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(logging.Formatter('%(asctime)s [HTTP_SNIPER] %(message)s'))
    logger.addHandler(fh)
    logger.addHandler(logging.StreamHandler(sys.stdout))

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
    normalized_price = round(target_price / tick_size) * tick_size
    return round(normalized_price, info.digits)

active_liquidations = set()

class TradeSignal(BaseModel):
    symbol: str
    direction: str
    conviction: Optional[float] = 0.80
    xgb_p: float = 0.5
    ddqn_p: float = 0.5
    hmm_state: str = "RANGE"
    timestamp: int
    reasoning: str = ""
    vpin: float = 0.0

@app.on_event("startup")
def startup_event():
    if not mt5.initialize():
        logger.critical("MT5 Initialization failed. Sniper cannot proceed.")
        sys.exit(1)
    
    # Level 6 SRE Patch: Explicitly subscribe to target portfolio symbols in MT5 Market Watch
    logger.info(f"[BOOT] Forcing MT5 Market Watch selection for {len(WATCHLIST)} portfolio symbols...")
    for sym in WATCHLIST:
        selected = mt5.symbol_select(sym, True)
        if not selected:
            logger.warning(f"⚠️ [WARNING] Failed to select {sym} in MT5 Market Watch.")
            
    # Directive 2: Terminal Status Check (v23.6)
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
async def execute_trade_endpoint(signal: TradeSignal):
    """Securely accepts and executes trade signals from the Oracle Brain."""
    logger.info(f"Received Signal: {signal.symbol} {signal.direction} (P={signal.conviction})")
    
    # 1. Staleness Check
    staleness = time.time() - signal.timestamp
    if staleness > STALENESS_THRESHOLD:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: STALE ({staleness:.1f}s old)")
        raise HTTPException(status_code=400, detail="Signal stale")

    # 2. Epistemic Gate
    norm_p = abs(signal.conviction - 0.5) + 0.5
    if norm_p < EPISTEMIC_GATE:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: NormP {norm_p:.3f} < {EPISTEMIC_GATE}")
        raise HTTPException(status_code=400, detail="Epistemic gate block")

    # 2b. Native MT5 Ledger Amnesia Lock Check (Level 14 SRE Refactoring)
    if is_amnesia_lock_active(signal.symbol, cooldown_seconds=300):
        logger.warning(f"[{signal.symbol}] Signal REJECTED: Amnesia Lock Active (Native MT5 Ledger Embargo)")
        raise HTTPException(status_code=429, detail="Amnesia Lock Active")

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
        logger.warning(f"[{signal.symbol}] Signal REJECTED: Order-Flow Toxicity Breached (VPIN={vpin_val:.3f} > 0.750). Embargoing entry.")
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
    success = perform_mt5_trade(signal.symbol, signal.direction, lot_size, signal.conviction)
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

    # D. MCP Risk Agent Check (v22.8)
    try:
        risk_url = "http://localhost:8001/check_trade"
        payload = {
            "symbol": symbol,
            "size_usd": incoming_notional,
            "leverage": 5,
            "xgb_p": xgb_p,
            "ddqn_p": ddqn_p
        }
        resp = risk_session.post(risk_url, json=payload, timeout=0.5)
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
            logger.error(f"[{symbol}] MCP Risk Agent unavailable (Status {resp.status_code}). Failing safe.")
            return False
    except Exception as e:
        logger.error(f"[{symbol}] MCP Risk Agent Connection Error: {e}. Failing safe.")
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
    current_atr, distance_to_swing = calculate_atr_and_swing(symbol, direction, lookback=20)
    spread = tick.ask - tick.bid
    spread_buffer = spread * 1.5
    sl_dist_price = max(1.2 * current_atr, distance_to_swing)
    
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
    
    logger.info(f"[{symbol}] DEBUG LOT: Balance={acc.balance:.2f} | MaxRisk=${max_dollar_risk:.2f} | KellyLot={kelly_lot} | AtrLot={atr_adjusted_lot} | FinalLot={lot}")

    if lot < info.volume_min and (risk_usd > 0 or max_dollar_risk > 0):
        # Verify if account can handle the margin for volume_min
        action_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        margin_req = mt5.order_calc_margin(action_type, symbol, info.volume_min, tick.ask)
        if margin_req and margin_req < acc.margin_free * 0.8:
            logger.info(f"[{symbol}] Small Account Floor: Forcing {lot} -> {info.volume_min}")
            lot = info.volume_min
        
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

def perform_mt5_trade(symbol, direction, lot, conviction):
    try:
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
        current_atr, distance_to_swing = calculate_atr_and_swing(symbol, direction, lookback=20)
        calculated_sl_dist = max(1.2 * current_atr, distance_to_swing)
        broker_minimum_sl = info.trade_stops_level * info.point if info else 0.0001
        final_sl_dist = max(calculated_sl_dist, broker_minimum_sl)
        
        logger.info(f"[{symbol}] CADES SL Validation: ATR={current_atr:.5f} | SwingDist={distance_to_swing:.5f} | FinalSL={final_sl_dist:.5f}")
        
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
                    "comment":      f"SENTINEL_AC_{i+1}of{len(valid_slices)}_P{conviction:.2f}",
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
                        positions = mt5.positions_get(ticket=ticket)
                        if positions:
                            pos = positions[0]
                            alpha_features = {}
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

                                # Directive 2: Apply the True ATR to the CADES Math with Grid Expansion
                                sl_dist = (1.2 * true_atr) * grid_expansion_scalar
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
                                    # Squash the TP target for mean-reverting chop environments
                                    # Aim for 0.4x to 0.8x ATR instead of 2.0x to 6.0x
                                    tp_dist = tp_dist * 0.15 
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
                                
                                # 4. MT5 Payload Architecture
                                request = {
                                    "action": mt5.TRADE_ACTION_SLTP,
                                    "symbol": pos.symbol,
                                    "position": pos.ticket,
                                    "sl": new_sl,
                                    "tp": new_tp
                                }
                                
                                # 5. Execution & Loud Logging with Exponential Backoff Retry Loop
                                max_retries = 3
                                attempt = 0
                                result = None
                                while attempt < max_retries:
                                    result = mt5.order_send(request)
                                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                                        break
                                    attempt += 1
                                    if attempt < max_retries:
                                        backoff_time = 0.1 * (2 ** attempt)
                                        logger.warning(f"⚠️ [MT5 RETRY] Ticket {pos.ticket} SL/TP mod failed (Retcode: {result.retcode if result else 'None'}). Retrying in {backoff_time:.2f}s (Attempt {attempt}/{max_retries})...")
                                        time.sleep(backoff_time)
                                        
                                if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                                    error_code = mt5.last_error()
                                    logger.critical(f"🚨 [PAGER ALERT] Ticket {pos.ticket} Exhausted 3 retries. Failed to attach SL/TP. Result: {result.retcode if result else 'None'}, MT5 Error: {error_code}")
                                    print(f"   -> Attempted SL: {new_sl}, Attempted TP: {new_tp}, Open Price: {pos.price_open}")
                                else:
                                    print(f"✅ [MT5 SUCCESS] Ticket {pos.ticket} SL/TP attached flawlessly.")
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
            "comment":      f"SENTINEL_v23.11_P{conviction:.2f}",
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
            request["comment"] = f"SENTINEL_FALLBACK_P{conviction:.2f}"
            
            res = mt5.order_send(request)

        if res is None:
            err = mt5.last_error()
            logger.critical(f"[FAIL] [CRITICAL_API_ERROR] {symbol} {direction} | mt5.order_send returned None. Last error: {err}")
            return False

        logger.info(f"[{symbol}] Broker Response: Retcode={res.retcode} | Comment={res.comment}")
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            ticket = getattr(res, 'order', getattr(res, 'deal', 0))
            logger.info(f"[OK] [EXECUTED] {symbol} {direction} {lot} lots at {price} filled ticket #{ticket}. Attaching SL/TP via ECN-Safe modification...")
            positions = mt5.positions_get(ticket=ticket)
            if positions:
                pos = positions[0]
                alpha_features = {}
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

                    # Directive 2: Apply the True ATR to the CADES Math with Grid Expansion
                    sl_dist = (1.2 * true_atr) * grid_expansion_scalar
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
                        # Squash the TP target for mean-reverting chop environments
                        # Aim for 0.4x to 0.8x ATR instead of 2.0x to 6.0x
                        tp_dist = tp_dist * 0.15 
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
                    
                    # 4. MT5 Payload Architecture
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": pos.symbol,
                        "position": pos.ticket,
                        "sl": new_sl,
                        "tp": new_tp
                    }
                    
                    # 5. Execution & Loud Logging with Exponential Backoff Retry Loop
                    max_retries = 3
                    attempt = 0
                    result = None
                    while attempt < max_retries:
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            break
                        attempt += 1
                        if attempt < max_retries:
                            backoff_time = 0.1 * (2 ** attempt)
                            logger.warning(f"⚠️ [MT5 RETRY] Ticket {pos.ticket} SL/TP mod failed (Retcode: {result.retcode if result else 'None'}). Retrying in {backoff_time:.2f}s (Attempt {attempt}/{max_retries})...")
                            time.sleep(backoff_time)
                            
                    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                        error_code = mt5.last_error()
                        logger.critical(f"🚨 [PAGER ALERT] Ticket {pos.ticket} Exhausted 3 retries. Failed to attach SL/TP. Result: {result.retcode if result else 'None'}, MT5 Error: {error_code}")
                        print(f"   -> Attempted SL: {new_sl}, Attempted TP: {new_tp}, Open Price: {pos.price_open}")
                    else:
                        print(f"✅ [MT5 SUCCESS] Ticket {pos.ticket} SL/TP attached flawlessly.")
            return True
        else:
            # Directive 1: Strict Retcode Logging (v23.6 Execution Autopsy)
            logger.critical(f"[FAIL] [BROKER_REJECTION] {symbol} {direction} | Retcode: {res.retcode} | Comment: {res.comment}")
            return False
            
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

