import MetaTrader5 as mt5
import sys

def rescue_crypto():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
    
    targets = ["LTCUSD", "XRPUSD"]
    for symbol in targets:
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            print(f"No positions for {symbol}")
            continue
        
        for pos in positions:
            if pos.sl != 0.0:
                print(f"{symbol} #{pos.ticket} already has SL={pos.sl}")
                continue
            
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                print(f"No tick for {symbol}")
                continue
            
            info = mt5.symbol_info(symbol)
            
            # Conservative rescue stops
            dist = tick.bid * 0.03 # 3%
            if pos.type == mt5.ORDER_TYPE_BUY:
                sl = tick.bid - dist
                tp = tick.bid + (dist * 2)
            else:
                sl = tick.ask + dist
                tp = tick.ask - (dist * 2)
            
            # Normalize
            sl = round(sl, info.digits)
            tp = round(tp, info.digits)
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": pos.ticket,
                "sl": sl,
                "tp": tp
            }
            
            res = mt5.order_send(request)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"RESCUED {symbol} #{pos.ticket}: SL={sl}, TP={tp}")
            else:
                print(f"FAILED {symbol} #{pos.ticket}: {res.retcode} {res.comment}")

    mt5.shutdown()

if __name__ == "__main__":
    rescue_crypto()
