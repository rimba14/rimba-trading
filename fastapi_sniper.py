"""
fastapi_sniper.py - Adaptive Sentinel Direct HTTP Execution Bridge (Machine B)
Ultra-Low-Latency, WebSocket-Free MT5 Execution Node (v19.2)

Exposes a REST API via FastAPI to receive signals from the Oracle VPS Brain.
Replaces the unstable Discord WebSocket bridge to eliminate 'Amnesia Locks'.
"""

import os
import json
import time
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import uvicorn
import MetaTrader5 as mt5
from dotenv import load_dotenv

# Load constitution/config
sys.path.append(r"C:\Sentinel_Project")
from sentinel_config import (
    WATCHLIST, KELLY_FRACTION, PORTFOLIO_HEAT_CAP, 
    LEVERAGE_WALL, STALENESS_THRESHOLD, EPISTEMIC_GATE, 
    MAGIC_NUMBER, HARD_RISK_CAP
)

load_dotenv()

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [HTTP_SNIPER] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("HttpSniper")

# FastAPI App Initialization
app = FastAPI(title="Adaptive Sentinel HTTP Sniper")

class TradeSignal(BaseModel):
    symbol: str
    direction: str
    conviction: float
    hmm_state: str = "RANGE"
    timestamp: int
    reasoning: str = ""

@app.on_event("startup")
def startup_event():
    if not mt5.initialize():
        logger.critical("MT5 Initialization failed. Sniper cannot proceed.")
        sys.exit(1)
    logger.info("MT5 Initialized. HTTP Sniper online.")

@app.on_event("shutdown")
def shutdown_event():
    mt5.shutdown()
    logger.info("MT5 Shutdown. Sniper offline.")

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

    # 3. Risk Gates
    if not check_risk_gates(signal.symbol, signal.direction, signal.hmm_state):
        raise HTTPException(status_code=403, detail="Risk gate block")

    # 4. Sizing & Execution
    lot_size = calculate_kelly_lot(signal.symbol, signal.conviction)
    if lot_size <= 0:
        logger.warning(f"[{signal.symbol}] Signal REJECTED: Lot size <= 0")
        raise HTTPException(status_code=400, detail="Invalid lot size")

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
    logger.info(f"Received EXIT Signal: {symbol} Ticket {ticket} Reason: {reason}")
    if execute_exit(ticket, symbol, reason):
        return {"status": "exited", "ticket": ticket}
    else:
        raise HTTPException(status_code=500, detail="Liquidation failed")

# -- Helper Logic (Ported from v17.9) ---------------------------------------- 

def check_risk_gates(symbol, direction, hmm_state):
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

    # C. Amnesia Lock
    if has_active_position_same_direction(symbol, direction):
        logger.warning(f"[{symbol}] Signal REJECTED: Amnesia Lock Active")
        return False

    # D. Margin & Leverage Check (Phase 4 - Leverage Wall <= 10x)
    acc = mt5.account_info()
    if acc:
        if acc.margin_level > 0 and acc.margin_level < 200:
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

def has_active_position_same_direction(symbol, direction):
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        for p in positions:
            if p.magic == MAGIC_NUMBER:
                pos_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                if pos_dir == direction:
                    return True
                else:
                    logger.warning(f"[{symbol}] Mutual Exclusion Triggered: Liquidating opposite {pos_dir} position #{p.ticket}")
                    execute_exit(p.ticket, symbol, "Mutual Exclusion")
    return False

def calculate_kelly_lot(symbol, conviction):
    info = mt5.symbol_info(symbol)
    acc = mt5.account_info()
    if not info or not acc: return 0.0
    p = abs(conviction - 0.5) + 0.5
    q = 1.0 - p
    f_star = p - (q / 1.5)
    # v19.1 Directive: Hard Risk Cap (<= 2.0%)
    f_final = min(max(0, f_star * KELLY_FRACTION), HARD_RISK_CAP) 
    risk_usd = acc.equity * f_final
    
    # Lot calc based on 1% price move (proxy)
    sl_dist_points = (info.ask * 0.01) / (info.point + 1e-12)
    point_val = info.trade_tick_value / (info.trade_tick_size / info.point)
    raw_vol = risk_usd / (sl_dist_points * point_val + 1e-12)
    lot = round(raw_vol / info.volume_step) * info.volume_step
    
    # v19.1 Directive: Small Account Execution Bypass
    # If lot < 0.01 but > 0, round up to 0.01
    if 0.0 < lot < 0.01:
        logger.info(f"[{symbol}] Small Account Bypass: Rounding {lot} up to 0.01")
        lot = 0.01
        
    lot = max(min(lot, info.volume_max), 0.0) 
    return lot

def perform_mt5_trade(symbol, direction, lot, p):
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return False
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "magic": MAGIC_NUMBER,
        "comment": f"SENTINEL_v18.4_P{p:.2f}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(request)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[OK] [EXECUTED] {symbol} {direction} {lot} lots at {price}")
        return True
    else:
        logger.error(f"[FAIL] [FAILED] {symbol} {direction} Error: {res.retcode} - {res.comment}")
        return False

def execute_exit(ticket, symbol, reason):
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
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[OK] [EXITED] {symbol} Ticket {ticket} Reason: {reason}")
        return True
    return False

if __name__ == "__main__":
    # Standard run on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
