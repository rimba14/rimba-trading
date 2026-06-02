import MetaTrader5 as mt5
import time

if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

trades = [
    {"symbol": "HK50", "action": mt5.ORDER_TYPE_BUY, "volume": 0.1, "sl": 24701.0, "tp": 26621.0},
    {"symbol": "GER40", "action": mt5.ORDER_TYPE_SELL, "volume": 0.1, "sl": 25747.68, "tp": 24399.22},
    {"symbol": "UNIUSD", "action": mt5.ORDER_TYPE_BUY, "volume": 0.59, "sl": 3.227, "tp": 3.688},
    {"symbol": "USDTRY", "action": mt5.ORDER_TYPE_BUY, "volume": 0.02, "sl": 45.53568, "tp": 46.01896},
    {"symbol": "DOTUSD", "action": mt5.ORDER_TYPE_BUY, "volume": 1.58, "sl": 1.235, "tp": 1.410}
]

for t in trades:
    sym = t["symbol"]
    # Ensure symbol is selected
    if not mt5.symbol_select(sym, True):
        print(f"Failed to select {sym}")
        continue
    
    symbol_info = mt5.symbol_info(sym)
    if symbol_info is None:
        print(f"{sym} not found")
        continue

    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        print(f"Could not get tick for {sym}")
        continue
        
    price = tick.ask if t["action"] == mt5.ORDER_TYPE_BUY else tick.bid
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": t["volume"],
        "type": t["action"],
        "price": price,
        "sl": t["sl"],
        "tp": t["tp"],
        "deviation": 20,
        "magic": 777777,
        "comment": "Sentinel Manual Execution",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to execute {sym}: {result.comment}")
    else:
        print(f"SUCCESS: Executed {sym} {t['action']} at {price}")
        
mt5.shutdown()
