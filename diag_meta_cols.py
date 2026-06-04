from arcticdb import Arctic
store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
lib = store["oracle_cache"]
data = lib.read("EURUSD_meta").data
print(data.tail(5)[["meta_conviction", "xgb_p", "ddqn_p"]])
