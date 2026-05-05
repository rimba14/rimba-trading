import sys
sys.path.append("C:/Sentinel_Project")
import git_arctic
import pandas as pd

def check_cache():
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    for sym in lib.list_symbols():
        print(f"Columns for {sym}:")
        df = lib.read(sym).data
        print(df.columns.tolist())
        break

if __name__ == "__main__":
    check_cache()
