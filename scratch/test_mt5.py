import MetaTrader5 as mt5
import json

if not mt5.initialize():
    print("MT5 Initialization Failed")
    exit(1)

symbol = "EURUSD" # Use a common symbol
info = mt5.symbol_info(symbol)
if not info:
    print(f"Symbol {symbol} not found")
    exit(1)

# Just check the price
tick = mt5.symbol_info_tick(symbol)
print(f"Current Bid for {symbol}: {tick.bid}")

mt5.shutdown()
