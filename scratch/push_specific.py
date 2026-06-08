import MetaTrader5 as mt5
import pandas as pd
from arcticdb import Arctic
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PUSH_SPECIFIC")

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

def push_trades():
    if not mt5.initialize():
        logger.error("MT5 initialization failed.")
        return

    targets = ["US2000", "USDZAR", "USDJPY", "AUDUSD", "ETHUSD"]
    
    store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
    lib = store["oracle_cache"]
    
    for sym in targets:
        info = mt5.symbol_info(sym)
        if not info:
            logger.error(f"[{sym}] Not found in MT5.")
            continue
            
        tick = mt5.symbol_info_tick(sym)
        if not tick or tick.ask <= 0 or tick.bid <= 0:
            logger.error(f"[{sym}] Invalid tick data.")
            continue
            
        # Get conviction from cache
        try:
            data = lib.read(sym + "_meta").data
            p_val = float(data.iloc[-1].get("meta_conviction", 0.5))
        except Exception:
            p_val = 0.5
            
        if p_val > 0.55:
            direction = "BUY"
        elif p_val < 0.45:
            direction = "SELL"
        else:
            logger.error(f"[{sym}] Conviction {p_val:.3f} is too weak for execution.")
            continue
            
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
            "comment": "MANUAL_PUSH",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[OK] {sym} {direction} | Entry: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Conv: {p_val:.3f} | Ticket: {res.order}")
        else:
            comment = res.comment if res else "Unknown Error"
            retcode = res.retcode if res else -1
            logger.error(f"[FAIL] {sym} {direction} - Error: {comment} ({retcode})")

    mt5.shutdown()

if __name__ == "__main__":
    push_trades()
