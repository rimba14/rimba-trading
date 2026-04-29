import MetaTrader5 as mt5
mt5.initialize()
symbols = mt5.symbols_get()
if symbols:
    print([s.name for s in symbols if "EUR" in s.name])
else:
    print("No symbols found.")
mt5.shutdown()
