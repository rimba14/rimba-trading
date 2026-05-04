import os
import sys
import asyncio
import logging
from pathlib import Path

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

import sentinel_slow_loop
from sentinel_config import WATCHLIST

def resume_trading():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [RESUME] %(message)s")
    
    print("\n" + "="*60)
    print("RESUMING TRADING: COGNITION WARM-UP (v18.9)")
    print("Bypassing Staleness Gate for Asian Market Opening...")
    print("="*60 + "\n")
    
    watchlist = WATCHLIST
    
    # We use the existing process_matrix_parallel with force_refresh=True
    # to unconditionally update all oracles and cure the weekend staleness.
    asyncio.run(sentinel_slow_loop.process_matrix_parallel(watchlist, force_refresh=True))
    
    print("\n" + "="*60)
    print("WARM-UP COMPLETE. All oracles updated with fresh market data.")
    print("The event-driven Slow Loop will now maintain live signals.")
    print("="*60 + "\n")

if __name__ == "__main__":
    resume_trading()
