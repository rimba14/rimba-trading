
import MetaTrader5 as mt5
import time
mt5.initialize()
tick = mt5.symbol_info_tick("BTCUSD")
print(f"Current Time: {int(time.time())}")
print(f"Tick Time:    {tick.time}")
print(f"Diff:         {int(time.time()) - tick.time}s")
mt5.shutdown()
