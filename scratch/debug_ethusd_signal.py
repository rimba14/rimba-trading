import os
import sys
import json
import logging
import pandas as pd

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

import sentinel_slow_loop
from sentinel_config import WATCHLIST, EPISTEMIC_GATE

def check_ethusd_signal():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIGNAL_CHECK] %(message)s")
    symbol = "ETHUSD"
    
    # 1. Read the latest meta from ArcticDB
    import git_arctic
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    
    try:
        item = lib.read(f"{symbol}_meta")
        data = item.data.iloc[-1]
        conviction = data['meta_conviction']
        state = data['hmm_state']
        p_dir = data['primary_dir']
        
        print(f"\n--- {symbol} SIGNAL ANALYSIS ---")
        print(f"Conviction: {conviction:.4f}")
        print(f"Regime: {state}")
        print(f"Primary Dir: {p_dir}")
        print(f"Epistemic Gate: {EPISTEMIC_GATE}")
        
        norm_p = abs(conviction - 0.5) + 0.5
        print(f"Normalized P: {norm_p:.4f}")
        
        if norm_p >= EPISTEMIC_GATE and p_dir != 0:
            print("[RESULT] Signal CROSSES the gate.")
            
            # Check Regime Alignment
            if state == "BEAR" and p_dir == 1:
                print("[BLOCK] Regime BEAR blocks BUY.")
            elif state == "BULL" and p_dir == -1:
                print("[BLOCK] Regime BULL blocks SELL.")
            else:
                print("[RESULT] Signal is ALIGNED with regime.")
                
                # Check for execution push
                print("Checking for signal delivery URL...")
                url = os.getenv("EXECUTION_ENDPOINT_URL")
                print(f"Execution URL: {url}")
                if not url:
                    print("[WARNING] No EXECUTION_ENDPOINT_URL found. Signal dropped to local queue.")
        else:
            print("[RESULT] Signal DOES NOT cross the gate.")
            
    except Exception as e:
        print(f"Error reading {symbol} meta: {e}")

if __name__ == "__main__":
    check_ethusd_signal()
