import os
import sys
import asyncio
import logging
import pandas as pd
from datetime import datetime, timezone

# Add project root to sys.path
sys.path.append(os.getcwd())

import sentinel_slow_loop
from sentinel_config import WATCHLIST

# Suppress noisy logging
logging.getLogger().setLevel(logging.WARNING)

async def scan_now():
    print(f"Initiating v27.0 Market Scan for {len(WATCHLIST)} assets...")
    # Run the parallel process matrix once
    await sentinel_slow_loop.process_matrix_parallel(WATCHLIST, force_refresh=True)
    
    # After scan, check ArcticDB
    from arcticdb import Arctic
    store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
    lib = store["oracle_cache"]
    
    results = []
    for symbol in WATCHLIST:
        try:
            item = lib.read(f"{symbol}_meta")
            if item is not None:
                data = item.data.iloc[-1]
                conviction = data.get("meta_conviction", 0.5)
                norm_p = abs(conviction - 0.5) + 0.5
                results.append({
                    "symbol": symbol,
                    "norm_p": norm_p,
                    "raw_p": conviction,
                    "state": data.get("hmm_state", "N/A")
                })
        except:
            pass
            
    results.sort(key=lambda x: x["norm_p"], reverse=True)
    print("\n[v27.0 SCAN RESULTS] Top Conviction Assets:")
    print(f"{'SYMBOL':<15} | {'NORM_P':<8} | {'STATE':<10}")
    print("-" * 40)
    for r in results[:10]:
        print(f"{r['symbol']:<15} | {r['norm_p']:<8.4f} | {r['state']:<10}")

if __name__ == "__main__":
    asyncio.run(scan_now())
