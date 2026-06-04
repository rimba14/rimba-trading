import MetaTrader5 as mt5
mt5.initialize()
syms = mt5.symbols_get()
for s in syms:
    if 'HK' in s.name or 'HANG' in s.name.upper() or 'HSI' in s.name.upper():
        print(s.name)
mt5.shutdown()
