import sys
import os
import time
from datetime import datetime, timezone
sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5
import git_arctic
import gitagent_utils as utils

def is_crypto(symbol):
    crypto_keywords = ["BTC", "ETH", "BCH", "LTC", "SOL", "XRP", "ADA", "DOGE", "DOT", "LINK", "UNI"]
    return any(k in symbol.upper() for k in crypto_keywords)

if not mt5.initialize():
    print("MT5 Init Failed")
    sys.exit()

store = git_arctic.get_arctic()
lib = store['oracle_cache']

assets = ['BTCUSD', 'ETHUSD', 'BCHUSD', 'LTCUSD', 'SOLUSD', 'XRPUSD', 'ADAUSD']

print(f"{'SYMBOL':<10} | {'PROB':<10} | {'HMM':<10} | {'CONVICTION':<10} | {'GATE_PASS'}")
print("-" * 65)

for s in assets:
    try:
        k_item = lib.read(f"{s}_kronos")
        h_item = lib.read(f"{s}_hmm")
        prob = k_item.data.iloc[-1].kronos_prob
        hmm = h_item.data.iloc[-1].state
        
        conviction = abs(prob - 0.5) + 0.5
        gate_pass = "YES" if conviction >= 0.82 else "NO"
        
        # Alignment check
        direction = "BUY" if prob > 0.5 else "SELL"
        alignment = True
        if hmm == 'BEAR' and direction == "BUY": alignment = False
        if hmm == 'BULL' and direction == "SELL": alignment = False
        
        if not alignment: gate_pass += " (Regime Block)"
        
        print(f"{s:<10} | {prob:<10.3f} | {hmm:<10} | {conviction:<10.3f} | {gate_pass}")
    except Exception as e:
        print(f"Error for {s}: {e}")

mt5.shutdown()
