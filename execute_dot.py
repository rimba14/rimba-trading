import MetaTrader5 as mt5

if not mt5.initialize():
    quit()

trades = [
    {"symbol": "DOTUSD", "action": mt5.ORDER_TYPE_BUY, "volume": 1.58, "sl": 1.17850, "tp": 1.50475}
]

for t in trades:
    sym = t["symbol"]
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
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
        "comment": "Sentinel Spread Adjust",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to execute {sym}: {result.comment}")
    else:
        print(f"SUCCESS: Executed {sym} {t['action']} at {price}")

mt5.shutdown()
