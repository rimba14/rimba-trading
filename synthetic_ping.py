import os
import json
import time
import requests
import logging
import sys
from dotenv import load_dotenv

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SYNTHETIC_PING] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SyntheticPing")

# Load configuration
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def fire_synthetic_ping():
    """Generates and fires a synthetic high-conviction signal into the Discord Bridge."""
    if not DISCORD_WEBHOOK_URL:
        logger.error("[ERROR] DISCORD_WEBHOOK_URL not found in .env. Please populate it.")
        return

    # Construct the signal matching the v17.5 schema
    signal_payload = {
        "symbol": "EURUSD",
        "direction": "BUY",  # Matching discord_listener.py enum
        "conviction": 0.99,
        "hmm_state": "BULL",
        "calculated_lot_size": 0.01,  # Telemetry
        "timestamp": int(time.time()),
        "version": "v17.5-PROD"
    }

    # Format for Discord Webhook (content field with code block)
    discord_payload = {
        "content": f"⚙️ **SYNTHETIC SRE SIGNAL INJECTION**\n```json\n{json.dumps(signal_payload, indent=2)}\n```"
    }

    try:
        logger.info(f"Firing synthetic signal for {signal_payload['symbol']}...")
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=discord_payload,
            timeout=10
        )

        if response.status_code in [200, 204]:
            logger.info(f"[SUCCESS] Synthetic Ping fired across the Discord Bridge. Status: {response.status_code}")
        else:
            logger.error(f"[ERROR] Webhook failed with status: {response.status_code} | Reason: {response.text}")

    except Exception as e:
        logger.error(f"[CRITICAL] Error firing synthetic ping: {e}")

if __name__ == "__main__":
    fire_synthetic_ping()
