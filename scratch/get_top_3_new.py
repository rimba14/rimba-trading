import MetaTrader5 as mt5
import pandas as pd
from arcticdb import Arctic
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TOP3_NEW")

def get_top_3():
    if not mt5.initialize():
        logger.error("MT5 initialization failed.")
        return

    # Get open positions
    open_positions = mt5.positions_get()
    open_symbols = set([pos.symbol for pos in open_positions]) if open_positions else set()

    store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
    if "oracle_cache" not in store.list_libraries():
        logger.error("Oracle cache library not found.")
        return
        
    lib = store["oracle_cache"]
    latest_signals = []
    
    symbols = lib.list_symbols()
    for sym in symbols:
        if not sym.endswith("_meta"):
            continue
            
        try:
            data = lib.read(sym).data
            if not data.empty:
                last_row = data.iloc[-1]
                p_val = float(last_row.get('meta_conviction', 0.5))
                if p_val != 0.5:
                    base_sym = sym.replace("_meta", "")
                    latest_signals.append({"symbol": base_sym, "conviction": p_val})
        except Exception:
            continue
            
    if not latest_signals:
        logger.error("No signals found in Oracle.")
        mt5.shutdown()
        return
        
    df_sig = pd.DataFrame(latest_signals)
    df_sig["strength"] = abs(df_sig["conviction"] - 0.5)
    df_sig = df_sig.sort_values(by="strength", ascending=False)
    
    valid_trades = []
    for _, row in df_sig.iterrows():
        sym = row["symbol"]
        conv = row["conviction"]
        
        if sym in open_symbols:
            continue
            
        info = mt5.symbol_info(sym)
        if not info:
            continue
            
        if conv > 0.55:
            direction = "BUY"
        elif conv < 0.45:
            direction = "SELL"
        else:
            continue
            
        valid_trades.append({
            "symbol": sym,
            "direction": direction,
            "conviction": conv
        })
        
        if len(valid_trades) == 3:
            break
            
    print("=========================================================")
    print("                TOP 3 NEW READY TRADES                   ")
    print("=========================================================")
    for i, t in enumerate(valid_trades, 1):
        print(f"{i}. Symbol: {t['symbol']} | Direction: {t['direction']} | Conviction: {t['conviction']:.3f}")

    mt5.shutdown()

if __name__ == "__main__":
    get_top_3()
