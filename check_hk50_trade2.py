import MetaTrader5 as mt5

if not mt5.initialize():
    quit()

sym = "HK50"
tick = mt5.symbol_info_tick(sym)
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": sym,
    "volume": 0.1,
    "type": mt5.ORDER_TYPE_BUY,
    "price": tick.ask,
    "sl": 24701.0,
    "tp": 26621.0,
    "deviation": 20,
    "magic": 777777,
    "comment": "Sentinel FOK Test",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_FOK,
}

result = mt5.order_send(request)
print("HK50 Retcode (FOK):", result.retcode if result else "None", "Comment:", result.comment if result else "None")

request["type_filling"] = mt5.ORDER_FILLING_RETURN
result2 = mt5.order_send(request)
print("HK50 Retcode (RETURN):", result2.retcode if result2 else "None", "Comment:", result2.comment if result2 else "None")

mt5.shutdown()
