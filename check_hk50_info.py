import MetaTrader5 as mt5
mt5.initialize()
info = mt5.symbol_info("HK50")
print("Min Volume:", info.volume_min, "Volume Step:", info.volume_step)
print("Trade Mode:", info.trade_mode)
print("Trade Execution:", info.trade_exemode) # 0: request, 1: instant, 2: market, 3: exchange
mt5.shutdown()
