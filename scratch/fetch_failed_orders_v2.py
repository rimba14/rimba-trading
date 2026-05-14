import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_failed_orders():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    from_date = datetime.now() - timedelta(days=3)
    orders = mt5.history_orders_get(from_date, datetime.now())
    
    if orders is None or len(orders) == 0:
        print("No orders found")
    else:
        df = pd.DataFrame(list(orders), columns=orders[0]._asdict().keys())
        print("Columns:", df.columns.tolist())
        # Filter for rejected/canceled
        # state 3=Canceled, 6=Rejected
        failed = df[df['state'].isin([3, 6])]
        print("\n--- RECENT ORDERS (Last 10) ---")
        # Try some common columns
        cols = ['time_setup', 'symbol', 'type', 'state', 'volume_initial', 'comment']
        # Intersect with available columns
        cols = [c for c in cols if c in df.columns]
        print(df[cols].tail(10).to_string())

    mt5.shutdown()

if __name__ == "__main__":
    get_failed_orders()
