import requests
import json
import time

payload = {
    "symbol": "BTCUSD",
    "direction": "BUY",
    "conviction": 0.85,
    "xgb_p": 0.85,
    "ddqn_p": 0.85,
    "timestamp": int(time.time())
}

try:
    resp = requests.post("http://localhost:8000/execute_trade", json=payload, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Request failed: {e}")
