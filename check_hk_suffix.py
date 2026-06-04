import MetaTrader5 as mt5
mt5.initialize()
syms = mt5.symbols_get()
for s in syms:
    if 'HK' in s.name:
        print(f"Name: {s.name}, Visible: {s.visible}, Time: {s.time}")
mt5.shutdown()
