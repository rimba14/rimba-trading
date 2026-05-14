import requests
import time

url = "http://localhost:8000/execute_trade"
payload = {
    "symbol": "EURUSD",
    "direction": "BUY",
    "conviction": 0.85,
    "hmm_state": "BULL",
    "timestamp": int(time.time()),
    "reasoning": "Manual SRE flow diagnostic for v22.8"
}

try:
    print(f"Sending signal to Sniper: {payload['symbol']}...")
    resp = requests.post(url, json=payload, timeout=5)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.json()}")
except Exception as e:
    print(f"Error: {e}")
