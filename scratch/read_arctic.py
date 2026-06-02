import MetaTrader5 as mt5
from arcticdb import Arctic

def get_arctic():
    try:
        store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
        lib = store["oracle_cache"]
        df = lib.read("NAS100_meta").data
        print(df.tail(1).to_dict('records'))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    get_arctic()
