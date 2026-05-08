"""
strategy_agent.py - STRATEGY EXECUTOR (v22.8 — MCP Microservice)
Monitors charts and executes technical strategy signals.

v22.8 MCP Architecture:
  - Exposed as a FastAPI microservice on port 8002.
  - The Hermes Orchestrator calls /scan asynchronously to query strategy signals
    without directly modifying sentinel_slow_loop.py or fastapi_sniper.py.
  - StrategyAgent class preserved for direct import compatibility.
  - Decoupled from Hyperliquid: accepts generic OHLCV dict for MT5/any source.
"""

import time
import logging
import numpy as np
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("StrategyAgent")


# ── Core Logic (preserved for direct import) ─────────────────────────────────

class StrategyAgent:
    """
    Stateless strategy signal generator.
    Takes a pre-fetched OHLCV dict and returns a (direction, reason) tuple.
    Decoupled from any specific broker (Hyperliquid, MT5, etc.).
    """

    def __init__(self, symbol: str = "", interval: str = "M15"):
        self.symbol   = symbol
        self.interval = interval

    def compute_bb_squeeze(self, closes: list) -> Tuple[bool, bool]:
        """
        Bollinger Band + Keltner Channel Squeeze detector.
        Returns (long_signal, short_signal).
        """
        if len(closes) < 20:
            return False, False

        arr   = np.array(closes, dtype=float)
        sma   = np.mean(arr[-20:])
        std   = np.std(arr[-20:])
        upper_bb = sma + 2 * std
        lower_bb = sma - 2 * std

        # Simple momentum proxy: last close vs 5-bar ago
        momentum = arr[-1] - arr[-6] if len(arr) >= 6 else 0.0

        squeeze_released = (upper_bb - lower_bb) > (std * 3.5)
        long_sig  = squeeze_released and momentum > 0
        short_sig = squeeze_released and momentum < 0

        return long_sig, short_sig

    def run(self, ohlcv_dict: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """
        Executes one strategy scan cycle.

        Args:
            ohlcv_dict: Optional pre-fetched dict with 'close' list. If None,
                        returns HOLD (live data fetching is broker-specific).

        Returns:
            (direction: str, reason: str) where direction in ["BUY", "SELL", "HOLD"].
        """
        if ohlcv_dict is None:
            logger.warning(f"[STRATEGY] No OHLCV data provided for {self.symbol}. Returning HOLD.")
            return "HOLD", "No data provided."

        closes = ohlcv_dict.get("close", [])
        if not closes:
            return "HOLD", "Empty close series."

        long_sig, short_sig = self.compute_bb_squeeze(closes)

        if long_sig:
            logger.info(f"[STRATEGY] LONG signal detected for {self.symbol}.")
            return "BUY", "BB Squeeze Breakout (Long)"
        elif short_sig:
            logger.info(f"[STRATEGY] SHORT signal detected for {self.symbol}.")
            return "SELL", "BB Squeeze Breakout (Short)"

        return "HOLD", "No squeeze release detected."


# ── MCP Server (FastAPI Microservice) ────────────────────────────────────────

def _start_mcp_server():
    """
    Starts the StrategyAgent as a FastAPI MCP microservice on port 8002.
    Called only when this file is executed directly.
    The Hermes Orchestrator calls /scan with an OHLCV payload via HTTP.
    """
    try:
        from fastapi import FastAPI
        from pydantic import BaseModel
        import uvicorn
        from typing import List

        app = FastAPI(title="Sentinel Strategy Agent MCP", version="22.8")

        class ScanRequest(BaseModel):
            symbol: str
            interval: str = "M15"
            closes: List[float] = []

        @app.get("/status")
        def status():
            return {
                "agent": "strategy_agent",
                "version": "v22.8",
                "timestamp": int(time.time()),
            }

        @app.post("/scan")
        def scan(req: ScanRequest):
            agent = StrategyAgent(symbol=req.symbol, interval=req.interval)
            direction, reason = agent.run(ohlcv_dict={"close": req.closes})
            return {
                "symbol": req.symbol,
                "direction": direction,
                "reason": reason,
                "timestamp": int(time.time()),
            }

        logger.info("[STRATEGY_AGENT_MCP] Starting on port 8002...")
        uvicorn.run(app, host="0.0.0.0", port=8002)

    except ImportError as e:
        logger.error(f"[STRATEGY_AGENT_MCP] FastAPI/uvicorn not available: {e}. Running in direct-import mode only.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [STRATEGY_AGENT] %(message)s")
    _start_mcp_server()
