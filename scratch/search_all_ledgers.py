import MetaTrader5 as mt5
import datetime

targets = {1314756980, 1314607796}

if not mt5.initialize():
    print("Failed to initialize MT5")
    exit(1)

print("Active Positions:")
positions = mt5.positions_get()
if positions:
    for p in positions:
        p_dict = p._asdict()
        if p.ticket in targets or p.identifier in targets:
            print(f"FOUND Active Position: {p_dict}")
        elif p.ticket == 1314756980 or p.ticket == 1314607796:
            print(f"FOUND Active Position Exact: {p_dict}")
        else:
            # Let's print any position to see
            print(f"Active Position: ticket={p.ticket}, symbol={p.symbol}, volume={p.volume}")
else:
    print("No active positions.")

print("\nActive Pending Orders:")
orders = mt5.orders_get()
if orders:
    for o in orders:
        if o.ticket in targets:
            print(f"FOUND Pending Order: {o._asdict()}")
else:
    print("No active pending orders.")

print("\nSearching historical deals globally (all)...")
from_date = datetime.datetime(2015, 1, 1)
to_date = datetime.datetime.now()
deals = mt5.history_deals_get(from_date, to_date)
if deals:
    print(f"Total deals scanned: {len(deals)}")
    found = False
    for d in deals:
        # Check all fields for targets
        d_dict = d._asdict()
        for k, v in d_dict.items():
            if v in targets:
                print(f"FOUND in Deal ticket={d.ticket}, field={k}, value={v}: {d_dict}")
                found = True
                break
    if not found:
        print("No historical deals matched the exact ticket numbers. Let's find closely matching deal comments or ticket prefixes...")
        # Check for partial ticket or comment matches
        for d in deals:
            d_dict = d._asdict()
            comment = d_dict.get('comment', '')
            if any(str(t)[:6] in comment or str(t)[:6] in str(d.position_id) or str(t)[:6] in str(d.order) for t in targets):
                print(f"Partial Match Deal: {d_dict}")
else:
    print("No historical deals retrieved.")

mt5.shutdown()
