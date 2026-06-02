import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

trades = [
    {"symbol": "BTCUSD", "action": mt5.ORDER_TYPE_BUY, "volume": 0.01, "sl": 76220.37, "tp": 79543.04},
    {"symbol": "GBPJPY", "action": mt5.ORDER_TYPE_BUY, "volume": 0.01, "sl": 213.465, "tp": 215.978}
]

for t in trades:
    sym = t["symbol"]
    if not mt5.symbol_select(sym, True):
        print(f"Failed to select {sym}")
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
