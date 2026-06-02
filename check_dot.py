import MetaTrader5 as mt5

mt5.initialize()
info = mt5.symbol_info("DOTUSD")
print(f"DOTUSD Trade Stops Level: {info.trade_stops_level}")
print(f"DOTUSD Point: {info.point}")
print(f"DOTUSD Digits: {info.digits}")

tick = mt5.symbol_info_tick("DOTUSD")
print(f"Ask: {tick.ask}, Bid: {tick.bid}")
mt5.shutdown()
