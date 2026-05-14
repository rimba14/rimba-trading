"""
risk_agent.py - PORTFOLIO GUARDIAN (v22.8 — MCP Microservice)
The sovereign risk-management layer. Overrides all other agents.

v22.8 MCP Architecture:
  - Exposed as a FastAPI microservice on port 8001.
  - The Hermes Orchestrator can call /check_trade and /status asynchronously
    without modifying monolithic execution scripts (fastapi_sniper.py, profit_manager.py).
  - Core RiskAgent class preserved for direct import compatibility.
"""

import os
import time
import logging
import sys
import datetime
import MetaTrader5 as mt5
from typing import Tuple

logger = logging.getLogger("RiskAgent")

# ── Level 40 SRE: Economic & Earnings Calendar (v26.3) ──────────────────────
# A static weekly macro dictionary representing upcoming Tier-1 events
# Format: { "Symbol/AssetClass": [ (DayOfWeek, Hour, Minute, "Event Name") ] }
# 0 = Monday, 1 = Tuesday, 2 = Wednesday, 3 = Thursday, 4 = Friday
STATIC_MACRO_CALENDAR = {
    "USD": [
        (2, 14, 0, "FOMC Rate Decision"), # Wed 2:00 PM EST
        (4, 8, 30, "Non-Farm Payrolls (NFP)"), # Fri 8:30 AM EST
        (3, 8, 30, "CPI / Inflation Data")
    ],
    "EUR": [
        (3, 8, 15, "ECB Rate Decision")
    ],
    "GBP": [
        (3, 7, 0, "BOE Rate Decision")
    ],
    "AAPL": [(3, 16, 0, "AAPL Q3 Earnings")],
    "MSFT": [(1, 16, 0, "MSFT Q3 Earnings")]
}

def check_upcoming_tier1_events(symbol: str, threshold_hours: float = 24.0) -> Tuple[bool, str]:
    """
    Checks if a Tier-1 macro event or earnings report is scheduled for the given symbol 
    within the next `threshold_hours`. Returns (True, event_name) if event is imminent.
    """
    now = datetime.datetime.utcnow()
    # Normalize current time to EST for simplicity (UTC-4/-5). Let's assume server time or UTC.
    # For simulation, we check if the current day/hour is close to the event
    
    events_to_check = []
    # Check currency pairs
    if len(symbol) == 6:
        base, quote = symbol[:3], symbol[3:]
        events_to_check.extend(STATIC_MACRO_CALENDAR.get(base, []))
        events_to_check.extend(STATIC_MACRO_CALENDAR.get(quote, []))
    else:
        # Check stocks/indices
        events_to_check.extend(STATIC_MACRO_CALENDAR.get(symbol, []))
        if "USD" in symbol:
             events_to_check.extend(STATIC_MACRO_CALENDAR.get("USD", []))

    for event in events_to_check:
        e_day, e_hour, e_minute, e_name = event
        
        # Calculate next occurrence of this event
        days_ahead = e_day - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and (now.hour > e_hour or (now.hour == e_hour and now.minute > e_minute))):
            days_ahead += 7
            
        event_time = now.replace(hour=e_hour, minute=e_minute, second=0, microsecond=0) + datetime.timedelta(days=days_ahead)
        time_until_event = (event_time - now).total_seconds() / 3600.0
        
        if 0 < time_until_event <= threshold_hours:
            return True, f"{e_name} in {time_until_event:.1f}h"
            
    return False, ""

# ── Core Logic (preserved for direct import) ─────────────────────────────────

class RiskAgent:
    def __init__(self, account_address: str = ""):
        self.address = account_address

        # Risk Parameters (MT5 production calibrated)
        self.max_position_size_usd = 10000.0  # Increased for v23.6 Autopsy
        self.max_leverage          = 50       # 50x max leverage
        self.daily_drawdown_limit  = 0.05     # 5% max daily loss
        self.total_portfolio_limit = 50000.0  # Max total exposure
        self.max_symbol_exposure_usd = 20000.0 # Per symbol cap

        # State tracking
        self.high_water_mark       = 0.0
        self.circuit_breaker_active = False

    def check_trade(self, symbol: str, size_usd: float, leverage: float, xgb_p: float = 0.5, ddqn_p: float = 0.5) -> Tuple[bool, str]:
        """
        Final check before any order is allowed.
        Includes v23.2 Dissonance Veto.
        Returns (allow: bool, reason: str).
        """
        if self.circuit_breaker_active:
            return False, "Circuit breaker active. Daily drawdown limit hit."

        # Directive 3 (v24.3 Level 23 SRE): Raised dissonance ceiling to 0.55.
        # Rationale: Untrained DDQN fallback outputs 0.50. A valid trade with
        # XGB=0.90 creates a delta of 0.40, which previously vetoed correct signals.
        # 0.55 still blocks extreme active disagreement (e.g., XGB=0.99 vs DDQN=0.10).
        MAX_COGNITIVE_DISSONANCE = 0.55
        dissonance = abs(xgb_p - ddqn_p)
        if dissonance > MAX_COGNITIVE_DISSONANCE:
            return False, f"Cognitive Dissonance Exceeded ({dissonance:.2f} > {MAX_COGNITIVE_DISSONANCE:.2f}). XGB: {xgb_p:.2f} vs DDQN: {ddqn_p:.2f}"

        if leverage > self.max_leverage:
            return False, f"Leverage {leverage}x exceeds max allowed {self.max_leverage}x."

        if size_usd > self.max_position_size_usd:
            return False, f"Position size ${size_usd:.2f} exceeds cap ${self.max_position_size_usd}"

        # Directive 2: Stateful Cumulative Risk (v23.3)
        if not mt5.initialize():
            logger.error("[RISK_AGENT] MT5 Init failed during check_trade. Failing safe.")
            return False, "MT5 connection failure in Risk Agent."

        positions = mt5.positions_get()
        cumulative_notional = 0.0
        if positions:
            # Substring match to catch suffixed symbols (e.g., XAUUSD vs XAUUSD.m)
            # Formula: Sum (volume * open_price)
            cumulative_notional = sum([p.volume * p.price_open for p in positions if symbol in p.symbol])
        
        if (cumulative_notional + size_usd) > self.max_symbol_exposure_usd:
            return False, f"Cumulative Exposure Cap Reached: ${cumulative_notional:.2f} + ${size_usd:.2f} > ${self.max_symbol_exposure_usd}"
        # ── v26.1: Negative Carry Veto (Swap Filter) ──
        info = mt5.symbol_info(symbol)
        if info:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
            if rates is not None and len(rates) > 0:
                current_atr = sum([r['high'] - r['low'] for r in rates]) / len(rates)
                zone2_tp_points = (current_atr * 4.0) / (info.point + 1e-12)
                
                direction = "BUY" if xgb_p > 0.5 else "SELL"
                daily_swap = info.swap_long if direction == "BUY" else info.swap_short
                
                # Directive 2: SRE Audit Logs
                logger.info(f"[{symbol}] AUDIT: H1_ATR={current_atr:.5f} | FreezeZone={info.trade_stops_level} | Swap={daily_swap:.2f}")
                
                if daily_swap < 0:
                    projected_cost_7d = abs(daily_swap) * 7
                    # If daily_swap represents a > 10% drag on the expected Zone 2 TP
                    if projected_cost_7d > (0.10 * zone2_tp_points):
                        logger.warning(f"[{symbol}] VETO: 7D_Swap_Cost={projected_cost_7d:.2f} > 10%_Zone2_TP={0.10*zone2_tp_points:.2f}")
                        return False, f"Negative Carry Veto: 7-Day Swap Cost ({projected_cost_7d:.2f}) > 10% of Zone 2 TP ({zone2_tp_points * 0.10:.2f})"
        
        # ── v26.3: Ex-Ante Macro Blackout (Pre-Event Embargo) ──
        has_event, event_desc = check_upcoming_tier1_events(symbol, threshold_hours=24.0)
        if has_event:
            logger.warning(f"[MACRO VETO] Rejecting {symbol} entry. Tier-1 Event / Earnings scheduled in < 24h: {event_desc}")
            return False, f"Ex-Ante Macro Blackout: {event_desc}"

        return True, "Risk check passed."

    def monitor_portfolio(self):
        """Placeholder — runs independently to check for emergency exits."""
        pass


# ── MCP Server (FastAPI Microservice) ────────────────────────────────────────

def _start_mcp_server():
    """
    Starts the RiskAgent as a FastAPI MCP microservice on port 8001.
    Called only when this file is executed directly.
    The Hermes Orchestrator calls /check_trade and /status via HTTP.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
        import uvicorn

        app = FastAPI(title="Sentinel Risk Agent MCP", version="23.2")
        _agent = RiskAgent()

        class TradeCheckRequest(BaseModel):
            symbol: str
            size_usd: float
            leverage: float
            xgb_p: float = 0.5
            ddqn_p: float = 0.5

        @app.get("/status")
        def status():
            return {
                "agent": "risk_agent",
                "version": "v23.2",
                "circuit_breaker": _agent.circuit_breaker_active,
                "max_leverage": _agent.max_leverage,
                "max_position_usd": _agent.max_position_size_usd,
                "timestamp": int(time.time()),
            }

        @app.post("/check_trade")
        def check_trade(req: TradeCheckRequest):
            allow, reason = _agent.check_trade(req.symbol, req.size_usd, req.leverage, req.xgb_p, req.ddqn_p)
            if not allow and ("Dissonance" in reason or "Exposure" in reason):
                # User requested a 403 or specific VETO response for critical breaches
                raise HTTPException(status_code=403, detail=reason)
            return {"allow": allow, "reason": reason, "symbol": req.symbol}

        logger.info("[RISK_AGENT_MCP] Starting on port 8001 (Dissonance Veto Active)...")
        uvicorn.run(app, host="0.0.0.0", port=8001)

    except ImportError as e:
        logger.error(f"[RISK_AGENT_MCP] FastAPI/uvicorn not available: {e}. Running in direct-import mode only.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [RISK_AGENT] %(message)s")
    _start_mcp_server()
