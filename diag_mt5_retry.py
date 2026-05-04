import MetaTrader5 as mt5
import time
import sys

def init_mt5():
    path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    for i in range(5):
        print(f"Attempt {i+1} to initialize MT5...")
        if mt5.initialize(path=path):
            print("SUCCESS")
            return True
        print(f"FAILED: {mt5.last_error()}")
        time.sleep(5)
    return False

if not init_mt5():
    sys.exit(1)

print(f"Version: {mt5.version()}")
account_info = mt5.account_info()
if account_info:
    print(f"Account: {account_info.login}")
    print(f"Server: {account_info.server}")
    print(f"Balance: {account_info.balance}")
else:
    print("No account info - possibly not logged in.")

mt5.shutdown()
