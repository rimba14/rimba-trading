from arcticdb import Arctic
import pandas as pd
store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")

print("Checking libraries...")
print(store.list_libraries())

if store.has_library("feature_store"):
    lib = store["feature_store"]
else:
    lib = store["oracle_cache"]

for symbol in ["EURUSD", "BTCUSD", "GBPUSD"]:
    key = f"features_{symbol}"
    if lib.has_symbol(key):
        df = lib.read(key).data.tail(10)
        print(f"\nAUDIT FOR {symbol}:")
        print(f"  NaN Count per Column: {df.isna().sum().to_dict()}")
    else:
        print(f"No feature vector found for {key} in {lib.name}")
