import MetaTrader5 as mt5
import time
from datetime import datetime

mt5.initialize()

for sym in ["EURUSD", "HK50", "US30", "XAUUSD", "BTCUSD"]:
    tick = mt5.symbol_info_tick(sym)
    if tick:
        dt = datetime.fromtimestamp(tick.time)
        print(f"{sym}: Last Tick Time = {dt} | Ask = {tick.ask}")
    else:
        print(f"{sym}: No tick data")

mt5.shutdown()
