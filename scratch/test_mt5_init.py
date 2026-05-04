import MetaTrader5 as mt5
import sys

if not mt5.initialize():
    print(f"MT5 Initialization Failed. Error: {mt5.last_error()}")
    sys.exit(1)

print("MT5 Initialization Success!")
print(f"Account Info: {mt5.account_info()}")
mt5.shutdown()
