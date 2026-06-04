import MetaTrader5 as mt5

if not mt5.initialize(): quit()

sym = "HK50"
tick = mt5.symbol_info_tick(sym)

request = {
    "action": mt5.TRADE_ACTION_PENDING,
    "symbol": sym,
    "volume": 0.1,
    "type": mt5.ORDER_TYPE_BUY_STOP,
    "price": tick.ask + 1.0,
    "sl": 24701.0,
    "tp": 26621.0,
    "magic": 777777,
    "comment": "Sentinel Pending Execution",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_RETURN,
}

result = mt5.order_send(request)
print("HK50 Pending Retcode:", result.retcode if result else "None", "Comment:", result.comment if result else "None")

mt5.shutdown()
