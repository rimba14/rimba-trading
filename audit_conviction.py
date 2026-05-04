import pandas as pd
from arcticdb import Arctic
import numpy as np

try:
    ac = Arctic('lmdb://c:/sentinel_arctic')
    lib = ac['oracle_cache']
    print("--- LATEST MARKET CONVICTION (Cache Audit) ---")
    symbols = ['EURUSD', 'BTCUSD', 'ETHUSD', 'XAUUSD', 'NAS100', 'SP500', 'GER40', 'GBPUSD', 'AUDUSD']
    for s in symbols:
        meta_sym = f"{s}_meta"
        if meta_sym in lib.list_symbols():
            df = lib.read(meta_sym).data
            if not df.empty:
                last_val = df.iloc[-1]
                p = last_val['meta_conviction']
                print(f"{s:7}: {p:.4f} | Direction: {'BUY' if p > 0.5 else 'SELL' if p < 0.5 else 'HOLD'}")
except Exception as e:
    print(f"Error reading ArcticDB: {e}")
