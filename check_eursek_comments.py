import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

positions = mt5.positions_get(symbol="EURSEK")
if not positions:
    # Try with suffix
    positions = mt5.positions_get()
    positions = [p for p in positions if "EURSEK" in p.symbol]

if not positions:
    print("No EURSEK positions found.")
else:
    print(f"{'TICKET':<12} | {'SYMBOL':<10} | {'COMMENT':<30} | {'TIME'}")
    print("-" * 70)
    for p in positions:
        print(f"{p.ticket:<12} | {p.symbol:<10} | {p.comment:<30} | {p.time}")

mt5.shutdown()
