import MetaTrader5 as mt5
import pandas as pd
from arcticdb import Arctic
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TOP1_PUSH")

def calculate_atr(symbol, timeframe=mt5.TIMEFRAME_H1, period=14):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 1)
    if rates is None or len(rates) < period:
        return 0.0
    
    df = pd.DataFrame(rates)
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    atr = df['tr'].rolling(window=period).mean().iloc[-1]
    return float(atr)

def push_top_1():
    if not mt5.initialize():
        logger.error("MT5 initialization failed.")
        return

    # Get open positions to filter out existing trades
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
            
        tick = mt5.symbol_info_tick(sym)
        if not tick or tick.ask <= 0 or tick.bid <= 0:
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
            "conviction": conv,
            "info": info,
            "tick": tick
        })
        
        if len(valid_trades) == 5:
            break
            
    logger.info("=========================================================")
    logger.info("                PUSHING TOP 1 NEW TRADE                  ")
    logger.info("=========================================================")
    
    for t in valid_trades:
        sym = t["symbol"]
        direction = t["direction"]
        info = t["info"]
        tick = t["tick"]
        
        price = tick.ask if direction == "BUY" else tick.bid
        atr = calculate_atr(sym)
        
        if atr == 0.0:
            logger.warning(f"[{sym}] Could not calculate ATR. Skipping.")
            continue
            
        sl_dist = 2.0 * atr
        tp_dist = 6.0 * atr
        
        if direction == "BUY":
            sl = price - sl_dist
            tp = price + tp_dist
            order_type = mt5.ORDER_TYPE_BUY
        else:
            sl = price + sl_dist
            tp = price - tp_dist
            order_type = mt5.ORDER_TYPE_SELL
            
        vol = info.volume_min
        
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": vol,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "magic": 777777,
            "comment": "TOP1_MACRO_SWING",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[OK] {sym} {direction} | Entry: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Conv: {t['conviction']:.3f} | Ticket: {res.order}")
            break # Successfully placed one trade
        else:
            comment = res.comment if res else "Unknown Error"
            retcode = res.retcode if res else -1
            logger.error(f"[FAIL] {sym} {direction} - Error: {comment} ({retcode})")
            if retcode == 10019:
                logger.warning(f"Not enough margin for {sym}. Trying next top signal...")
                continue
            break

    mt5.shutdown()

if __name__ == "__main__":
    push_top_1()
