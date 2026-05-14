import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_failed_orders():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    # Look back 3 days
    from_date = datetime.now() - timedelta(days=3)
    orders = mt5.history_orders_get(from_date, datetime.now())
    
    if orders is None:
        print("No orders found")
    else:
        df = pd.DataFrame(list(orders), columns=orders[0]._asdict().keys())
        # Filter for orders that are NOT filled
        # state: 1=STARTED, 2=PLACED, 3=CANCELED, 4=PARTIAL, 5=FILLED, 6=REJECTED, 7=EXPIRED
        # We want rejected or canceled
        failed = df[df['state'].isin([3, 6, 7])]
        print("--- FAILED ORDERS ---")
        print(failed[['time_setup', 'symbol', 'type', 'state', 'price_setup', 'volume_initial', 'comment']].tail(10).to_string())
        
        print("\n--- ALL RECENT ORDERS ---")
        print(df[['time_setup', 'symbol', 'type', 'state', 'price_setup', 'volume_initial', 'comment']].tail(10).to_string())

    mt5.shutdown()

if __name__ == "__main__":
    get_failed_orders()
