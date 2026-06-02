import MetaTrader5 as mt5
import sys

if not mt5.initialize():
    print("MT5 initialization failed")
    sys.exit(1)

trades = [
    {"symbol": "HK50", "action": mt5.ORDER_TYPE_BUY, "volume": 0.1, "sl": 24783.0, "tp": 26703.0},
    {"symbol": "GBPUSD", "action": mt5.ORDER_TYPE_BUY, "volume": 0.01, "sl": 1.34115, "tp": 1.35551},
    {"symbol": "EURCHF", "action": mt5.ORDER_TYPE_BUY, "volume": 0.02, "sl": 0.90996, "tp": 0.91819}
]

for t in trades:
    sym = t["symbol"]
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
        "comment": "Sentinel Manual Push",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to execute {sym}: {result.retcode} - {result.comment}")
    else:
        print(f"SUCCESS: Executed {sym} {t['action']} at {price} | SL: {t['sl']} | TP: {t['tp']}")
        
mt5.shutdown()
