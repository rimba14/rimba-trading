import MetaTrader5 as mt5
mt5.initialize()
tick = mt5.symbol_info_tick('EURUSD')
print(tick.ask)
