import profit_manager
import inspect

print("--- profit_manager globals ---")
for name in dir(profit_manager):
    if not name.startswith('_'):
        val = getattr(profit_manager, name)
        if not inspect.isfunction(val) and not inspect.isclass(val):
            print(f"{name} = {val}")

# Try to find SL_ATR_MULT and TP_ATR_MULT
try:
    print(f"SL_ATR_MULT = {profit_manager.SL_ATR_MULT}")
except AttributeError:
    print("SL_ATR_MULT not found in globals.")

try:
    print(f"TP_ATR_MULT = {profit_manager.TP_ATR_MULT}")
except AttributeError:
    print("TP_ATR_MULT not found in globals.")
