import requests
import json
import time
import sys
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.append(r"C:\Sentinel_Project")
from math_meta_model import MathMetaModel

def run_synthetic_test():
    print("[SYNTHETIC TEST] Initializing Golden Setup Injection for EURUSD...")
    
    mm = MathMetaModel()
    
    # Directive 1: Mock the Macro Context for EURUSD
    # We monkey-patch the _get_macro_context to return our "Golden" catalyst
    def mock_macro_context(symbol):
        # [sentiment, risk, catalyst]
        # In v19.2, these are dampened with np.log1p
        # Catalyst 0.99 -> approx 0.69 after dampener
        return 0.5, 0.1, 0.99
    
    mm._get_macro_context = mock_macro_context
    
    # Define "Perfect Market Anomaly" features
    # Z_XGB=3.5, Z_KRONOS=3.5, HMM=BULL, FAISS=0.95
    xgb_z = 3.5
    kronos_z = 3.5
    hmm_state = "BULL"
    faiss_sim = 0.95
    
    print(f"[TEST] Inputs: Z_XGB={xgb_z}, Z_KRONOS={kronos_z}, HMM={hmm_state}, FAISS={faiss_sim}")
    
    # Generate Conviction Score (P)
    conviction = mm.predict_conviction("EURUSD", xgb_z, kronos_z, hmm_state, faiss_sim)
    print(f"[TEST] Calculated Meta-Conviction (P): {conviction:.6f}")
    
    # Check against the gate (0.816)
    gate = 0.816
    norm_p = abs(conviction - 0.5) + 0.5
    print(f"[TEST] Norm_P: {norm_p:.6f} | Gate: {gate:.3f}")
    
    if norm_p >= gate:
        print("[GATE BREACH] Signal verified. Initiating HTTP Bridge execution...")
        
        # Prepare payload for fastapi_sniper
        payload = {
            "symbol": "EURUSD",
            "direction": "BUY",
            "conviction": round(conviction, 6),
            "hmm_state": hmm_state,
            "atr": 0.00125,
            "timestamp": int(time.time()),
            "version": "v19.2-SYNTHETIC-TEST",
            "dry_run": True # Safeguard: Ensure execution node only logs
        }
        
        # Local execution tunnel URL (Machine B)
        url = "http://localhost:8000/execute_trade"
        
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                print(f"[BRIDGE SUCCESS] FastAPI 200 OK. Response: {response.json()}")
            else:
                print(f"[BRIDGE FAILURE] FastAPI Status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[BRIDGE ERROR] Connectivity failure: {e}")
    else:
        print("[GATE BLOCKED] Conviction failed to breach the 0.816 gate. Check Meta-Model weights.")

if __name__ == "__main__":
    run_synthetic_test()
