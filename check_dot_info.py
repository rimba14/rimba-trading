import MetaTrader5 as mt5
mt5.initialize()
print(mt5.symbol_info("DOTUSD")._asdict())
mt5.shutdown()
