import MetaTrader5 as mt5
import sys

path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
if not mt5.initialize(path=path):
    print(f"FAILED: {mt5.last_error()}")
    sys.exit(1)

print("SUCCESS")
print(f"Version: {mt5.version()}")
print(f"Terminal Info: {mt5.terminal_info()}")
mt5.shutdown()
