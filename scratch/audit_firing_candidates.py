import os
import sys
from datetime import datetime
import pandas as pd
import numpy as np

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
from sentinel_config import WATCHLIST, EPISTEMIC_GATE

def audit_firing_candidates():
    try:
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        
        candidates = []
        
        for sym in WATCHLIST:
            try:
                # Read latest meta
                item = lib.read(f"{sym}_meta")
                data = item.data.iloc[-1]
                
                conviction = data['meta_conviction']
                state = data['hmm_state']
                p_dir = data['primary_dir']
                ts = data['timestamp']
                
                norm_p = abs(conviction - 0.5) + 0.5
                dist = EPISTEMIC_GATE - norm_p
                age = int(datetime.now().timestamp() - ts)
                
                # Check for Regime Block
                blocked = False
                if state == "BEAR" and p_dir == 1: blocked = True
                if state == "BULL" and p_dir == -1: blocked = True
                
                candidates.append({
                    "SYMBOL": sym,
                    "DIR": "BUY" if p_dir == 1 else ("SELL" if p_dir == -1 else "HOLD"),
                    "REGIME": state,
                    "CONVICTION": norm_p,
                    "GATE_DIST": dist,
                    "AGE": age,
                    "STATUS": "BLOCKED" if blocked else ("READY" if dist <= 0 else "WARMING")
                })
            except:
                continue
        
        # Sort by distance to gate (closest first)
        df = pd.DataFrame(candidates)
        if df.empty:
            print("No active signals found in cache.")
            return
            
        df = df.sort_values("GATE_DIST", ascending=True)
        
        print("\n" + "="*85)
        print(f"{'SYMBOL':<10} | {'DIR':<6} | {'REGIME':<8} | {'CONVICTION':<10} | {'GATE_DIST':<10} | {'AGE':<6} | {'STATUS':<8}")
        print("-" * 85)
        
        for _, row in df.head(15).iterrows():
            print(f"{row['SYMBOL']:<10} | {row['DIR']:<6} | {row['REGIME']:<8} | {row['CONVICTION']:<10.4f} | {row['GATE_DIST']:<10.4f} | {row['AGE']:<5}s | {row['STATUS']:<8}")
        print("="*85 + "\n")
        
    except Exception as e:
        print(f"AUDIT_ERR: {e}")

if __name__ == "__main__":
    audit_firing_candidates()
