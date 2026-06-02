import MetaTrader5 as mt5
import datetime

tickets = [1314756980, 1314607796]

print("Initializing MT5...")
if not mt5.initialize():
    print(f"Failed to initialize MT5, error: {mt5.last_error()}")
    exit(1)

print("MT5 initialized successfully.")

# Query all history since 2020
from_date = datetime.datetime(2020, 1, 1)
to_date = datetime.datetime.now()

print(f"Querying history from {from_date} to {to_date}...")

deals = mt5.history_deals_get(from_date, to_date)
if deals is None:
    print("Failed to get history deals.")
else:
    print(f"Retrieved {len(deals)} total deals in history.")
    found_deals = []
    for d in deals:
        if d.position_id in tickets or d.order in tickets or d.ticket in tickets:
            found_deals.append(d)
    
    if found_deals:
        print(f"\nFound {len(found_deals)} deals matching the target tickets:")
        for fd in found_deals:
            d_dict = fd._asdict()
            d_dict['time_readable'] = str(datetime.datetime.fromtimestamp(d_dict['time']))
            print(d_dict)
    else:
        print("No matching deals found in history. Let's look at the most recent 10 closed deals:")
        # Sort deals by time descending
        sorted_deals = sorted(deals, key=lambda x: x.time, reverse=True)
        # Filter for entry OUT or deals with profit to represent closed trades
        closed_deals = [d for d in sorted_deals if d.entry == mt5.DEAL_ENTRY_OUT or d.profit != 0.0]
        for d in closed_deals[:10]:
            d_dict = d._asdict()
            d_dict['time_readable'] = str(datetime.datetime.fromtimestamp(d_dict['time']))
            print(d_dict)

mt5.shutdown()
