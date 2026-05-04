import os
import sys
import json
import requests
from dotenv import load_dotenv

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
load_dotenv()

def manual_push_eth():
    symbol = "ETHUSD"
    conviction = 0.8432
    state = "BULL"
    p_dir = 1
    
    payload = {
        "symbol":             symbol,
        "direction":          "BUY",
        "conviction":         round(float(conviction), 4),
        "kronos_conviction":  round(float(conviction), 4),
        "hmm_state":          state,
        "atr":                50.0,
        "timestamp":          int(1778111111), # Synthetic timestamp
        "version":            "v18.9-DEBUG",
    }
    
    url = os.getenv("EXECUTION_ENDPOINT_URL")
    if not url:
        print("ERROR: EXECUTION_ENDPOINT_URL not found.")
        return
        
    print(f"Pushing synthetic ETHUSD signal to {url}...")
    try:
        # Use the same format as sentinel_slow_loop._post_to_sniper
        response = requests.post(url, json=payload, timeout=10)
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.text}")
        if response.status_code == 200:
            print("✅ Signal delivered successfully.")
        else:
            print("❌ Signal delivery failed.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    manual_push_eth()
