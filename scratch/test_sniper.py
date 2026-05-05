import requests
import time

url = "http://127.0.0.1:8000/execute_trade"
payload = {
    "symbol": "USDCNH",
    "direction": "BUY",
    "conviction": 0.7058,
    "hmm_state": "RANGE",
    "timestamp": int(time.time()),
    "reasoning": "SRE TEST"
}

try:
    resp = requests.post(url, json=payload, timeout=5)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
except Exception as e:
    print(f"Error: {e}")
