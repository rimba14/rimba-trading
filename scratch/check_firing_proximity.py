import os
import sys
sys.path.append(os.getcwd())
import pandas as pd
from arcticdb import Arctic
from sentinel_config import WATCHLIST
from datetime import datetime, timezone

def check_conviction():
    try:
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        lib = store["oracle_cache"]
    except Exception as e:
        print(f"Error accessing ArcticDB: {e}")
        return

    results = []
    for symbol in WATCHLIST:
        try:
            item = lib.read(f"{symbol}_meta")
            if item is not None:
                data = item.data.iloc[-1]
                conviction = data.get("meta_conviction", 0.5)
                norm_p = abs(conviction - 0.5) + 0.5
                ts = data.get("timestamp", 0)
                state = data.get("hmm_state", "UNKNOWN")
                
                # Check if signal is recent (within last 1 hour)
                now = datetime.now(timezone.utc).timestamp()
                age = now - ts
                
                results.append({
                    "symbol": symbol,
                    "conviction": conviction,
                    "norm_p": norm_p,
                    "state": state,
                    "age_sec": age,
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                })
        except:
            pass

    # Sort by norm_p descending (closest to firing)
    results.sort(key=lambda x: x["norm_p"], reverse=True)
    
    print(f"{'SYMBOL':<15} | {'NORM_P':<8} | {'RAW_P':<8} | {'STATE':<10} | {'AGE(s)':<8}")
    print("-" * 60)
    for r in results[:15]:
        print(f"{r['symbol']:<15} | {r['norm_p']:<8.4f} | {r['conviction']:<8.4f} | {r['state']:<10} | {int(r['age_sec']):<8}")

if __name__ == "__main__":
    check_conviction()
