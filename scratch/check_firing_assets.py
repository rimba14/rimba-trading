import pandas as pd
from arcticdb import Arctic
import logging
import os

# Suppress arcticdb logs
logging.getLogger("arcticdb").setLevel(logging.ERROR)

def check_signals():
    ARCTIC_DIR = "lmdb://C:/Sentinel_Project/data/arctic_cache"
    try:
        store = Arctic(ARCTIC_DIR)
        lib = store["oracle_cache"]
    except Exception as e:
        print(f"Error connecting to ArcticDB: {e}")
        return

    print(f"{'Asset':<10} | {'P-Score':<8} | {'Regime':<8} | {'Status':<15}")
    print("-" * 50)

    results = []
    
    # Base Epistemic Gate from config
    EPISTEMIC_GATE = 0.60
    RANGE_GATE = 0.75

    for key in lib.list_symbols():
        if key.endswith("_meta"):
            symbol = key.replace("_meta", "")
            try:
                item = lib.read(key)
                if item.data.empty: continue
                row = item.data.iloc[-1]
                
                meta_p = float(row["meta_conviction"])
                hmm_state = str(row["hmm_state"])
                
                # Estimate gate (using 50/50 split as a proxy if weights aren't cached)
                # In real loop it's dynamic based on MixTS weights
                gate = 0.619 # Typical value from logs
                
                distance = 0.0
                direction = "NEUTRAL"
                
                if meta_p > 0.5:
                    direction = "BUY"
                    distance = meta_p - gate
                else:
                    direction = "SELL"
                    distance = (1.0 - meta_p) - gate
                
                results.append({
                    "symbol": symbol,
                    "meta_p": meta_p,
                    "hmm_state": hmm_state,
                    "direction": direction,
                    "distance": distance
                })
            except Exception:
                continue

    # Sort by distance (closest to gate first)
    # We want results where distance is closest to 0 or positive
    results.sort(key=lambda x: x["distance"], reverse=True)

    for r in results[:10]:
        status = "FIRING!" if r["distance"] >= 0 else f"{-r['distance']:.4f} away"
        print(f"{r['symbol']:<10} | {r['meta_p']:<8.4f} | {r['hmm_state']:<8} | {r['direction']:<5} {status}")

if __name__ == "__main__":
    check_signals()
