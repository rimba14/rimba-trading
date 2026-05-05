from arcticdb import Arctic
import pandas as pd
import os
from dotenv import load_dotenv

ARCTIC_DIR = "lmdb://C:/Sentinel_Project/data/arctic_cache"
load_dotenv("C:/Sentinel_Project/.env")

# Watchlist from sentinel_config
WATCHLIST = [
    "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD", "BCHUSD", "XRPUSD", "ADAUSD", "DOTUSD",
    "MATICUSD", "DOGEUSD", "UNIUSD", "ATOMUSD", "TRXUSD",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY",
    "EURCHF", "AUDJPY", "NZDJPY", "CHFJPY", "EURAUD", "GBPAUD", "USDMXN", "USDZAR", "USDTRY", "EURNOK",
    "EURSEK", "USDCNH", "USDSGD", "USDHKD", "EURPLN",
    "SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40", "XAUUSD", "XAGUSD", "CL-OIL"
]

def check_conviction_spikes():
    try:
        store = Arctic(ARCTIC_DIR)
        lib = store["oracle_cache"]
    except Exception as e:
        print(f"FAILED ArcticDB connection: {e}")
        return

    results = []
    for symbol in WATCHLIST:
        try:
            item = lib.read(f"{symbol}_meta")
            row = item.data.iloc[-1]
            conviction = float(row["meta_conviction"])
            hmm_state = str(row["hmm_state"])
            results.append({
                "symbol": symbol,
                "conviction": conviction,
                "hmm": hmm_state
            })
        except:
            continue

    df = pd.DataFrame(results)
    # Sort by conviction descending
    df_sorted = df.sort_values(by="conviction", ascending=False)
    
    print("--- CONVICTION SPIKE AUDIT ---")
    print(df_sorted.head(15).to_string(index=False))

if __name__ == "__main__":
    check_conviction_spikes()
