import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, time as dt_time
import google.generativeai as genai
import requests
from pathlib import Path
from dotenv import load_dotenv

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

load_dotenv()

# --- Config ---
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
MACRO_STATE_FILE = PROJECT_ROOT / "data" / "macro_state.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Logging
import io as _io
def _get_utf8_stream():
    if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
        return sys.stdout
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except Exception:
        return _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

_UTF8_STREAM = _get_utf8_stream()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DEEP_RESEARCH] %(message)s",
    handlers=[
        logging.StreamHandler(_UTF8_STREAM),
        logging.FileHandler(PROJECT_ROOT / "data" / "deep_research.log", encoding="utf-8")
    ]
)

def _get_watchlist():
    # Fallback to standard 50-asset list if sentinel_config is not available
    try:
        from sentinel_config import WATCHLIST
        return WATCHLIST
    except ImportError:
        return ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "HK50", "NAS100", "SP500", "XAUUSD", "CL-OIL"]

async def fetch_macro_oracle():
    """Triggers the Gemini Deep Research Oracle for fundamental macro synthesis."""
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY missing. Deep Research Oracle inactive.")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('models/gemini-flash-latest') 

    watchlist = _get_watchlist()
    
    prompt = f"""
    Perform a Deep Macro Research synthesis for the current global market regime.
    
    Target Assets: {', '.join(watchlist[:50])}
    
    Analysis Requirements:
    1. Assess current Fed Monetary Policy and interest rate expectations (dot plot, terminal rate).
    2. Evaluate global liquidity cycles and risk-on/risk-off sentiment.
    3. Identify specific fundamental catalysts for the listed assets (e.g., ETF flows for BTC, NFP for USD, Earnings for NAS100).
    4. Explicitly quantify "Black Swan Risk" (probability of tail-risk events like systemic banking failure, geopolitical escalation, or flash crashes).

    CONSTITUTIONAL REQUIREMENT: Your output MUST be a valid JSON object. 
    Strict Schema:
    {{
        "global_macro_sentiment": float (-1.0 to 1.0),
        "black_swan_risk": float (0.0 to 1.0),
        "asset_specific_catalysts": {{
            "SYMBOL": float (-1.0 to 1.0),
            ... (for each symbol)
        }}
    }}
    
    Do not include any text outside the JSON block.
    """

    try:
        logging.info("Triggering Gemini Deep Research Oracle...")
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean potential markdown code blocks
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()

        macro_data = json.loads(text)
        
        # Add metadata
        macro_data["timestamp"] = int(datetime.now(timezone.utc).timestamp())
        macro_data["last_update_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Save to cache
        MACRO_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MACRO_STATE_FILE, 'w') as f:
            json.dump(macro_data, f, indent=4)
            
        logging.info(f"Macro state updated successfully. Black Swan Risk: {macro_data.get('black_swan_risk'):.2f}")
        
        # --- High-Risk Liquidation Trigger ---
        if macro_data.get("black_swan_risk", 0.0) > 0.85:
            logging.critical("[BLACK_SWAN] Systemic risk detected! Triggering global liquidation...")
            url = os.getenv("EXECUTION_ENDPOINT_URL")
            if url:
                try:
                    # In v18.9, the /liquidate endpoint expects a ticket or broad command
                    # We'll send a signal that the Fast Loop handles as 'ALL' if symbol is '*'
                    requests.post(f"{url}/liquidate", json={"symbol": "*", "reason": "BLACK_SWAN_SYSTEMIC_RISK"}, timeout=10)
                    logging.info("[OK] Liquidation command broadcast successfully.")
                except Exception as ex:
                    logging.error(f"[FAIL] Failed to broadcast liquidation: {ex}")
        
    except Exception as e:
        logging.error(f"Deep Research Oracle failed: {e}")

async def run_daemon():
    logging.info("Deep Research Daemon starting (24h loop)...")
    
    # Run once at startup to hydrate cache
    await fetch_macro_oracle()
    
    while True:
        now = datetime.now(timezone.utc)
        # Calculate seconds until next 00:00 UTC
        next_run = datetime.combine(now.date(), dt_time(0, 0), tzinfo=timezone.utc)
        if next_run <= now:
            # If 00:00 passed today, target tomorrow
            from datetime import timedelta
            next_run += timedelta(days=1)
        
        sleep_seconds = (next_run - now).total_seconds()
        logging.info(f"Next research cycle in {sleep_seconds/3600:.1f} hours.")
        await asyncio.sleep(sleep_seconds)
        await fetch_macro_oracle()

if __name__ == "__main__":
    asyncio.run(run_daemon())
