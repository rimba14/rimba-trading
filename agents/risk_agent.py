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
import MetaTrader5 as mt5
from typing import Tuple

logger = logging.getLogger("RiskAgent")

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

        # Directive 2: Dissonance Veto Calibration (v23.2 Hotfix)
        max_dissonance = 0.40 if symbol == 'XAUUSD' else 0.50
        dissonance = abs(xgb_p - ddqn_p)
        if dissonance > max_dissonance:
            return False, f"Cognitive Dissonance Exceeded ({dissonance:.2f} > {max_dissonance:.2f}). XGB: {xgb_p:.2f} vs DDQN: {ddqn_p:.2f}"

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
