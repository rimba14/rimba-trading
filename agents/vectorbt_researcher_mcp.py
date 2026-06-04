import os
import json
import time
import logging
import sys
import pandas as pd
import numpy as np
from mcp.server.fastmcp import FastMCP
from vectorbt_researcher_mcp import run_parameter_sweep as core_run_parameter_sweep

# Initialize the FastMCP server for Hermes
mcp = FastMCP("Sentinel Quant Researcher")

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
try:
    import gitagent_utils as utils
except ImportError:
    utils = None

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

@mcp.tool()
def run_parameter_sweep(symbol: str, timeframe: str = 'M15', lookback_days: int = 30) -> str:
    """
    Asynchronous Quant Researcher: Runs parameter sweeps using VectorBT.
    Identifies superior ATR/Kelly configurations based on historical data.
    """
    result = core_run_parameter_sweep(symbol, timeframe, lookback_days)
    return json.dumps(result, indent=2)

def send_research_webhook(symbol, config, sharpe, total_ret):
    """Pushes a Research Webhook to Discord."""
    try:
        import requests
        payload = {
            "embeds": [{
                "title": f"🔬 QUANT RESEARCH: New Edge Detected",
                "description": f"**Symbol:** `{symbol}`\n**Config:** `{config}`\n**Sharpe:** `{sharpe:.2f}`\n**Return:** `{total_ret:.2%}`",
                "color": 0x3498DB, # Blue for research
                "footer": {"text": "Adaptive Sentinel v15.1 | VectorBT Engine"}
            }]
        }
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except:
        pass

if __name__ == "__main__":
    mcp.run()
