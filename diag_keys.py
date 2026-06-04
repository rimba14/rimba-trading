from arcticdb import Arctic
store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
lib = store["oracle_cache"]
keys = lib.list_symbols()
print("Total keys:", len(keys))
print("Sample keys:", keys[:20])
