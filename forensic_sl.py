import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta

if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

ticket = 1056526854
print(f"--- FORENSIC REPORT | Ticket: {ticket} ---")

# 1. Check if STILL OPEN
pos = mt5.positions_get(ticket=ticket)
if pos:
    print("\n[LIVE] Position is still OPEN.")
    print(pos[0]._asdict())
else:
    print("\n[CLOSED] Position is not open. Checking history...")
    from_date = datetime.now(timezone.utc) - timedelta(hours=2)
    deals = mt5.history_deals_get(from_date, datetime.now(timezone.utc))
    if deals:
        for d in deals:
            if d.position_id == ticket:
                print(f"Match found! Deal: {d._asdict()}")
    else:
        print("No matches in history.")

# 2. Analyze Price Action
rates = mt5.copy_rates_from_pos("USDCAD", mt5.TIMEFRAME_M1, 0, 100)
if rates is not None:
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    print("\nRecent M1 Price Action (Last 5 mins):")
    print(df.tail(5)[['time', 'open', 'high', 'low', 'close']])
    print(f"\nLowest Low in last 60 mins: {df['low'].min()}")

mt5.shutdown()
