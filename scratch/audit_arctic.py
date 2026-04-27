import sys
import os
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import pandas as pd

def audit():
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    symbols = lib.list_symbols()
    print(f"Total symbols in oracle_cache: {len(symbols)}")
    
    from sentinel_config import WATCHLIST
    print(f"Watchlist size: {len(WATCHLIST)}")
    
    for sym in WATCHLIST[:5]: # Check first 5
        k_key = f"{sym}_kronos"
        if k_key in symbols:
            df = lib.read(k_key).data
            last_row = df.iloc[-1]
            print(f"[{sym}] Key found: {k_key}")
            print(f"  Kronos Prob: {last_row.get('kronos_prob')}")
            print(f"  XGBoost Prob: {last_row.get('xgboost_prob')}")
            print(f"  Timestamp: {last_row.get('timestamp')}")
        else:
            print(f"[{sym}] Key NOT found: {k_key}")
            # Search for similar keys
            matches = [s for s in symbols if sym in s]
            print(f"  Similar keys: {matches}")

if __name__ == "__main__":
    audit()
