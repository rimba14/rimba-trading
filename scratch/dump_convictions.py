
import sys
import os
sys.path.append(r'C:\Sentinel_Project')
import git_arctic
import pandas as pd

ac = git_arctic.get_arctic()
lib = ac['oracle_cache']
symbols = lib.list_symbols()
meta_symbols = [s for s in symbols if '_meta' in s]

print("--- CURRENT SENTINEL CONVICTIONS ---")
for s in meta_symbols:
    try:
        data = lib.read(s).data
        last = data.iloc[-1]
        print(f"{s:20} | Conviction: {last['meta_conviction']:.3f} | Dir: {last['primary_dir']}")
    except:
        pass
