import sys
from pathlib import Path
import pandas as pd
import time
from arcticdb import Arctic

# Add project root to path
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
sys.path.append(str(PROJECT_ROOT))

def audit_hot_crypto():
    try:
        ac = Arctic("lmdb://./data/arctic_cache")
        lib = ac["oracle_cache"]
    except Exception as e:
        print(f"Error connecting to ArcticDB: {e}")
        return

    crypto_symbols = [
        "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", 
        "LTCUSD", "BCHUSD", "XRPUSD", "ADAUSD", "DOTUSD"
    ]
    
    # Check MT5 symbols (they might have suffixes)
    # For now we'll check the base ones and look for suffixes if they fail
    
    print(f"{'SYMBOL':<10} | {'DIR':<5} | {'CONVICTION':<10} | {'GATE_DIST':<10} | {'AGE(s)':<6}")
    print("-" * 50)
    
    now = time.time()
    for sym in crypto_symbols:
        # Check standard and common suffixes
        found = False
        for suffix in ["", ".m", ".pro", "+"]:
            key = f"{sym}{suffix}_meta"
            if key in lib.list_symbols():
                try:
                    df = lib.read(key).data
                    if df.empty: continue
                    
                    last = df.iloc[-1]
                    conv = float(last["meta_conviction"])
                    norm_p = abs(conv - 0.5) + 0.5
                    gate_dist = 0.82 - norm_p
                    age = now - float(last["timestamp"])
                    direction = "BUY" if last["primary_dir"] == 1 else ("SELL" if last["primary_dir"] == -1 else "HOLD")
                    
                    print(f"{sym+suffix:<10} | {direction:<5} | {conv:<10.4f} | {gate_dist:<10.4f} | {age:<6.0f}")
                    found = True
                    break
                except: pass
        if not found:
            # print(f"{sym:<10} | N/A")
            pass

if __name__ == "__main__":
    audit_hot_crypto()
