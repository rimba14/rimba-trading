import os
import sys
from datetime import datetime
import pandas as pd

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic

def get_signals_update():
    # Use the expanded 50-asset watchlist concept (sampling key assets)
    watchlist = [
        "BTCUSD", "ETHUSD", "SOLUSD", 
        "HK50", "USDJPY", "AUDUSD", "EURUSD",
        "XAUUSD", "NAS100"
    ]
    
    try:
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        print("\n" + "="*60)
        print(f"{'SYMBOL':<10} | {'REGIME':<8} | {'CONVICTION':<10} | {'AGE':<6}")
        print("-" * 60)
        
        for sym in watchlist:
            try:
                # Get HMM State
                h_item = lib.read(f"{sym}_hmm")
                h_data = h_item.data.iloc[-1]
                
                # Get Kronos Probability
                k_item = lib.read(f"{sym}_kronos")
                k_data = k_item.data.iloc[-1]
                
                age = int(datetime.now().timestamp() - k_data['timestamp'])
                prob = k_data['kronos_prob']
                state = h_data['state']
                
                print(f"{sym:<10} | {state:<8} | {prob:<10.3f} | {age:<5}s")
            except:
                print(f"{sym:<10} | {'NO_DATA':<8} | {'N/A':<10} | {'N/A':<5}")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"ARCTIC_DB_ERR: {e}")

if __name__ == "__main__":
    get_signals_update()
