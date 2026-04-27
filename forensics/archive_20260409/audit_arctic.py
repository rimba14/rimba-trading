from arcticdb import Arctic
import pandas as pd

try:
    ac = Arctic("lmdb://C:\\sentinel_arctic")
    
    # 1. Audit 'trading_data' (Ticks/Bars)
    if "trading_data" in ac.list_libraries():
        lib_data = ac.get_library("trading_data")
        symbols = lib_data.list_symbols()
        print(f"--- TRADING DATA AUDIT ---")
        print(f"Symbols found: {len(symbols)}")
        for s in symbols[:5]:
            rows = len(lib_data.read(s).data)
            print(f" - {s}: {rows} rows")
    
    # 2. Audit 'trading_edge' (Scores)
    if "trading_edge" in ac.list_libraries():
        lib_edge = ac.get_library("trading_edge")
        edge_symbols = lib_edge.list_symbols()
        print(f"\n--- TRADING EDGE AUDIT ---")
        print(f"Symbols found: {len(edge_symbols)}")
        for s in edge_symbols[:5]:
            rows = len(lib_edge.read(s).data)
            print(f" - {s}: {rows} scores recorded")
            
except Exception as e:
    print(f"Audit Error: {e}")
