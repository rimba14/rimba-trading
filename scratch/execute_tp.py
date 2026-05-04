import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

def liquidate_ticket(symbol, ticket, reason):
    url = os.getenv("EXECUTION_ENDPOINT_URL")
    if not url:
        print("EXECUTION_ENDPOINT_URL not found")
        return
    
    # The /liquidate endpoint in fastapi_sniper.py expects:
    # { "symbol": symbol, "ticket": ticket, "reason": reason }
    payload = {
        "symbol": symbol,
        "ticket": int(ticket),
        "reason": reason
    }
    
    try:
        # Note: fastapi_sniper.py /liquidate endpoint is at f"{url}/liquidate"
        # Wait, if url is http://.../execute_trade, I need the base.
        base_url = url.replace("/execute_trade", "")
        target = f"{base_url}/liquidate"
        
        resp = requests.post(target, json=payload, timeout=5)
        if resp.status_code == 200:
            print(f"[SUCCESS] Liquidated {symbol} #{ticket}: {reason}")
        else:
            print(f"[FAILED] {symbol} #{ticket}: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[ERROR] {symbol} #{ticket}: {e}")

if __name__ == "__main__":
    targets = [
        ("BTCUSD", 1254871784, "Thesis Decay (TP)"),
        ("GER40", 1254661514, "Regime Conflict (TP)"),
        ("HK50", 1255276375, "Regime Conflict (TP)"),
        ("NAS100", 1254885171, "Thesis Decay (Exit)")
    ]
    
    for symbol, ticket, reason in targets:
        liquidate_ticket(symbol, ticket, reason)
        time.sleep(0.5)
