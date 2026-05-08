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
from typing import Tuple

logger = logging.getLogger("RiskAgent")

# ── Core Logic (preserved for direct import) ─────────────────────────────────

class RiskAgent:
    def __init__(self, account_address: str = ""):
        self.address = account_address

        # Risk Parameters (MT5 production calibrated)
        self.max_position_size_usd = 50.0    # Cap per trade
        self.max_leverage          = 5       # 5x isolated max
        self.daily_drawdown_limit  = 0.05    # 5% max daily loss
        self.total_portfolio_limit = 500.0   # Max total notional exposure

        # State tracking
        self.high_water_mark       = 0.0
        self.circuit_breaker_active = False

    def check_trade(self, symbol: str, size_usd: float, leverage: float) -> Tuple[bool, str]:
        """
        Final check before any order is allowed.
        Returns (allow: bool, reason: str).
        """
        if self.circuit_breaker_active:
            return False, "Circuit breaker active. Daily drawdown limit hit."

        if leverage > self.max_leverage:
            return False, f"Leverage {leverage}x exceeds max allowed {self.max_leverage}x."

        if size_usd > self.max_position_size_usd:
            return False, f"Position size ${size_usd} exceeds cap ${self.max_position_size_usd}."

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
        from fastapi import FastAPI
        from pydantic import BaseModel
        import uvicorn

        app = FastAPI(title="Sentinel Risk Agent MCP", version="22.8")
        _agent = RiskAgent()

        class TradeCheckRequest(BaseModel):
            symbol: str
            size_usd: float
            leverage: float

        @app.get("/status")
        def status():
            return {
                "agent": "risk_agent",
                "version": "v22.8",
                "circuit_breaker": _agent.circuit_breaker_active,
                "max_leverage": _agent.max_leverage,
                "max_position_usd": _agent.max_position_size_usd,
                "timestamp": int(time.time()),
            }

        @app.post("/check_trade")
        def check_trade(req: TradeCheckRequest):
            allow, reason = _agent.check_trade(req.symbol, req.size_usd, req.leverage)
            return {"allow": allow, "reason": reason, "symbol": req.symbol}

        logger.info("[RISK_AGENT_MCP] Starting on port 8001...")
        uvicorn.run(app, host="0.0.0.0", port=8001)

    except ImportError as e:
        logger.error(f"[RISK_AGENT_MCP] FastAPI/uvicorn not available: {e}. Running in direct-import mode only.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [RISK_AGENT] %(message)s")
    _start_mcp_server()
