import MetaTrader5 as mt5
import datetime

pos_id = 1314050134

if not mt5.initialize():
    print("Failed to initialize MT5")
    exit(1)

from_date = datetime.datetime(2020, 1, 1)
to_date = datetime.datetime.now()

deals = mt5.history_deals_get(from_date, to_date)
if deals:
    print(f"--- SCANNING DEALS FOR POSITION {pos_id} ---")
    pos_deals = [d for d in deals if d.position_id == pos_id]
    for d in pos_deals:
        d_dict = d._asdict()
        d_dict['time_readable'] = str(datetime.datetime.fromtimestamp(d_dict['time']))
        print(d_dict)
        
    print("\n--- SCANNING ORDERS FOR POSITION ---")
    orders = mt5.history_orders_get(from_date, to_date)
    if orders:
        pos_orders = [o for o in orders if o.position_id == pos_id]
        for o in pos_orders:
            o_dict = o._asdict()
            o_dict['time_setup_readable'] = str(datetime.datetime.fromtimestamp(o_dict['time_setup']))
            print(o_dict)
            
mt5.shutdown()
