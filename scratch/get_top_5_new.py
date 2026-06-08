import MetaTrader5 as mt5
import pandas as pd
from arcticdb import Arctic

def get_top_5():
    mt5.initialize()
    open_positions = mt5.positions_get()
    open_symbols = set([pos.symbol for pos in open_positions]) if open_positions else set()
    store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
    lib = store["oracle_cache"]
    latest_signals = []
    
    for sym in lib.list_symbols():
        if not sym.endswith("_meta"): continue
        try:
            data = lib.read(sym).data
            if not data.empty:
                p_val = float(data.iloc[-1].get("meta_conviction", 0.5))
                if p_val != 0.5:
                    latest_signals.append({"symbol": sym.replace("_meta", ""), "conviction": p_val})
        except Exception: pass

    df_sig = pd.DataFrame(latest_signals)
    df_sig["strength"] = abs(df_sig["conviction"] - 0.5)
    df_sig = df_sig.sort_values(by="strength", ascending=False)
    
    valid_trades = []
    for _, row in df_sig.iterrows():
        sym = row["symbol"]
        if sym in open_symbols: continue
        if not mt5.symbol_info(sym): continue
        if row["conviction"] > 0.55: dir_ = "BUY"
        elif row["conviction"] < 0.45: dir_ = "SELL"
        else: continue
        
        valid_trades.append({"symbol": sym, "direction": dir_, "conviction": row["conviction"]})
        if len(valid_trades) == 5: break

    print("=========================================================")
    print("                TOP 5 NEW READY TRADES                   ")
    print("=========================================================")
    for i, t in enumerate(valid_trades, 1):
        print(f"{i}. Symbol: {t['symbol']} | Direction: {t['direction']} | Conviction: {t['conviction']:.3f}")
    
    mt5.shutdown()

if __name__ == "__main__":
    get_top_5()
