from arcticdb import Arctic
store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
lib = store["oracle_cache"]
assets = []
for sym in lib.list_symbols():
    if sym.endswith("_meta"):
        data = lib.read(sym).data
        if not data.empty:
            p_val = float(data.iloc[-1].get("xgb_p", 0.5))
            assets.append((sym, p_val))
print("Available convictions:", assets[:10])
