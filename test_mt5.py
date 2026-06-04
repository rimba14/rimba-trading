import MetaTrader5 as mt5

# Connect to MT5
if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()
    quit()

print("MT5 initialized")
