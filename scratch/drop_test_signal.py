import json
import time
import os

signal = {
    "symbol": "BCHUSD",
    "direction": "BUY",
    "kronos_conviction": 0.99,
    "hmm_state": "BULL",
    "vol_pct": 0.21,
    "atr": 0.65,
    "base_atr": 0.65,
    "timestamp": time.time()
}

signal_dir = r"C:\Sentinel_Project\pending_signals"
os.makedirs(signal_dir, exist_ok=True)
signal_file = os.path.join(signal_dir, "BCHUSD_TEST_v2.json")

with open(signal_file, "w") as f:
    json.dump(signal, f)

print(f"[TEST] Signal dropped: {signal_file}")
