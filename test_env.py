import sys
print("Python version:", sys.version)
import MetaTrader5 as mt5
print("MT5 version:", mt5.__version__)
if mt5.initialize():
    print("MT5 initialized successfully")
    mt5.shutdown()
else:
    print("MT5 initialization failed:", mt5.last_error())
