import sys
from arcticdb import Arctic

ARCTIC_DIR = "lmdb://C:/Sentinel_Project/data/arctic_cache"

def dump_keys():
    try:
        store = Arctic(ARCTIC_DIR)
        lib = store["oracle_cache"]
        symbols = lib.list_symbols()
        print("Symbols in cache:", [s for s in symbols if "BTC" in s or "ETH" in s])
        
        btc_sym = "BTCUSD_meta"
        if btc_sym not in symbols:
            # try to find one
            for s in symbols:
                if "BTC" in s:
                    btc_sym = s
                    break

        if btc_sym in symbols:
            item = lib.read(btc_sym)
            df = item.data
            if not df.empty:
                row = df.iloc[-1]
                print(f"\nKeys for {btc_sym}:")
                for k, v in row.items():
                    print(f"{k}: {v}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    dump_keys()
