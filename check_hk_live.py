import MetaTrader5 as mt5
import time

mt5.initialize()
tick1 = mt5.symbol_info_tick("HK50")
time.sleep(2)
tick2 = mt5.symbol_info_tick("HK50")
print(f"Tick 1: {tick1.time_msc}, Ask: {tick1.ask}")
print(f"Tick 2: {tick2.time_msc}, Ask: {tick2.ask}")
mt5.shutdown()
