import requests
import time

url = "http://127.0.0.1:8000/execute_trade"
payload = {
    "symbol": "XAUUSD",
    "direction": "BUY",
    "conviction": 0.85,
    "xgb_p": 0.85,
    "ddqn_p": 0.5,
    "hmm_state": "BULL",
    "timestamp": int(time.time()),
    "reasoning": "SRE Diagnostic Test - Lot Size Debug"
}

print(f"Sending test signal for XAUUSD to {url}...")
try:
    resp = requests.post(url, json=payload, timeout=5)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
