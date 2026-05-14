import requests
import time

signal = {
    'symbol': 'XAUUSD',
    'direction': 'BUY',
    'conviction': 0.85,
    'xgb_p': 0.85,
    'ddqn_p': 0.85,
    'hmm_state': 'BULL',
    'timestamp': int(time.time()),
    'reasoning': 'SRE Live Ignition Trace'
}

try:
    resp = requests.post('http://localhost:8000/execute_trade', json=signal)
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
