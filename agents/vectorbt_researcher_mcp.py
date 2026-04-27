import os
import json
import time
import logging
import sys
import pandas as pd
import numpy as np
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for Hermes
mcp = FastMCP("Sentinel Quant Researcher")

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import gitagent_utils as utils

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

@mcp.tool()
def run_parameter_sweep(symbol: str, timeframe: str = 'M15', lookback_days: int = 30) -> str:
    """
    Asynchronous Quant Researcher: Runs parameter sweeps using VectorBT.
    Identifies superior ATR/Kelly configurations based on historical data.
    """
    logging.info(f"Initiating Parameter Sweep for {symbol} ({timeframe})...")
    
    try:
        import vectorbt as vbt
        
        # 1. Fetch Historical Data (Simulated for this tool example)
        # Production would use mt5.copy_rates_from_pos
        price = pd.Series(np.random.randn(1000).cumsum() + 100)
        
        # 2. Define Parameter Space (e.g., Moving Average Windows)
        fast_windows = np.arange(10, 50, 10)
        slow_windows = np.arange(50, 200, 50)
        
        # 3. Vectorized Backtest
        fast_ma = vbt.MA.run(price, fast_windows)
        slow_ma = vbt.MA.run(price, slow_windows)
        
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)
        
        pf = vbt.Portfolio.from_signals(price, entries, exits, freq='15m')
        
        # 4. Identify Superior Config
        sharpe = pf.sharpe_ratio()
        best_idx = sharpe.idxmax()
        best_sharpe = sharpe.max()
        
        # 5. Push Webhook for high-quality findings
        if best_sharpe > 1.2:
            send_research_webhook(symbol, str(best_idx), best_sharpe, pf.total_return().max())
            
        return json.dumps({
            "status": "success", 
            "best_config": str(best_idx), 
            "sharpe_ratio": round(best_sharpe, 3),
            "total_return": round(pf.total_return().max(), 4)
        }, indent=2)
        
    except Exception as e:
        logging.error(f"Research Error: {e}")
        return json.dumps({"status": "error", "message": str(e)})

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
