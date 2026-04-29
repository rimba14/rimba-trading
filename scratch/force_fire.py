import MetaTrader5 as mt5
import sys

def force_fire(symbol, side, volume=0.1):
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
    
    # Check if symbol is available
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"Symbol {symbol} not found")
        return
    
    if not info.visible:
        mt5.symbol_select(symbol, True)
    
    price = mt5.symbol_info_tick(symbol).ask if side == "BUY" else mt5.symbol_info_tick(symbol).bid
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "magic": 17300,
        "comment": "FORCE_FIRE_v17.3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    res = mt5.order_send(request)
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {res.comment}")
    else:
        print(f"Order executed: {res.order}")
    
    mt5.shutdown()

if __name__ == "__main__":
    force_fire("GBPUSD", "BUY")
