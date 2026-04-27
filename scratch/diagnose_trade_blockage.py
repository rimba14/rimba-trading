
import sys
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import time
from sentinel_config import WATCHLIST
import MetaTrader5 as mt5

def diagnose():
    print("=== SENTINEL TRADE BLOCKAGE DIAGNOSTIC ===")
    now = time.time()
    ac = git_arctic.get_arctic()
    cache = ac['oracle_cache']
    
    # 1. Check Staleness
    print("\n--- Phase 1: Cache Staleness ---")
    stale_count = 0
    for s in WATCHLIST:
        try:
            h_ts = cache.read(f"{s}_hmm").data.iloc[-1].get("timestamp", 0)
            staleness = now - h_ts
            status = "STALE" if staleness > 360 else "FRESH"
            print(f"{s}: {int(staleness)}s ({status})")
            if staleness > 360: stale_count += 1
        except:
            print(f"{s}: NO DATA")
            stale_count += 1
            
    # 2. Check Conviction Levels
    print("\n--- Phase 2: Conviction Audit ---")
    high_conv_count = 0
    for s in WATCHLIST:
        try:
            m_item = cache.read(f"{s}_meta").data.iloc[-1]
            conv = m_item.get('meta_conviction', 0)
            if conv > 0.70:
                print(f"{s}: {conv:.4f} (CLOSE!)")
                high_conv_count += 1
            else:
                pass
        except:
            pass
            
    # 3. Check MT5 Connection & Terminal Status
    print("\n--- Phase 3: MT5 & Terminal ---")
    if not mt5.initialize():
        print("MT5: FAILED TO INITIALIZE")
    else:
        info = mt5.terminal_info()
        print(f"MT5 Connected: {info.connected}")
        print(f"MT5 Trade Allowed: {info.trade_allowed}")
        mt5.shutdown()

    # 4. Final Verdict
    print("\n--- FINAL DIAGNOSTIC VERDICT ---")
    if stale_count == len(WATCHLIST):
        print("CRITICAL: The entire oracle cache is STALE (>360s).")
        print("REASON: sentinel_slow_loop.py is likely not processing Dollar Bars.")
        print("ACTION: Verify if InformationBarStreamer is receiving volume/ticks.")
    elif high_conv_count == 0:
        print("NEUTRAL: No assets have crossed the 0.82 Epistemic Gate.")
        print("REASON: Low conviction across the board. The system is protecting capital.")
    else:
        print("Check Fast Loop (chat_gemma.py) logs for regime or amnesia blocks.")

if __name__ == "__main__":
    diagnose()
