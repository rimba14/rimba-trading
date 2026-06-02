import MetaTrader5 as mt5
from datetime import datetime, timezone
import pandas as pd

def search_anywhere():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    # From Jan 1, 1970 to now
    from_date = datetime(1970, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    
    print(f"Searching MT5 history from {from_date} to {now}...")
    
    # 1. Search in history deals
    deals = mt5.history_deals_get(from_date, now)
    if deals:
        df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        target_deals = df_deals[(df_deals['ticket'] == 1314684045) | (df_deals['position_id'] == 1314684045) | (df_deals['order'] == 1314684045)]
        if not target_deals.empty:
            print("\n=== FOUND IN HISTORY DEALS ===")
            for idx, row in target_deals.iterrows():
                d_time = datetime.fromtimestamp(row['time'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                print(f"Deal Ticket: {row['ticket']}")
                print(f"  Symbol:    {row['symbol']}")
                print(f"  Time:      {d_time}")
                print(f"  Entry:     {'IN' if row['entry'] == mt5.DEAL_ENTRY_IN else 'OUT' if row['entry'] == mt5.DEAL_ENTRY_OUT else 'IN/OUT'}")
                print(f"  Type:      {'BUY' if row['type'] == mt5.ORDER_TYPE_BUY else 'SELL'}")
                print(f"  Volume:    {row['volume']}")
                print(f"  Price:     {row['price']}")
                print(f"  Profit:    {row['profit']} USD")
                print(f"  Comment:   {row['comment']}")
                print(f"  Position:  {row['position_id']}")
                print(f"  Order:     {row['order']}")
                
    # 2. Search in history orders
    orders = mt5.history_orders_get(from_date, now)
    if orders:
        df_orders = pd.DataFrame(list(orders), columns=orders[0]._asdict().keys())
        target_orders = df_orders[(df_orders['ticket'] == 1314684045) | (df_orders['position_id'] == 1314684045)]
        if not target_orders.empty:
            print("\n=== FOUND IN HISTORY ORDERS ===")
            for idx, row in target_orders.iterrows():
                o_time = datetime.fromtimestamp(row['time_setup'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                print(f"Order Ticket: {row['ticket']}")
                print(f"  Symbol:     {row['symbol']}")
                print(f"  Setup Time: {o_time}")
                print(f"  State:      {row['state']}")
                print(f"  Type:       {row['type']}")
                print(f"  Volume:     {row['volume_initial']}")
                print(f"  Price:      {row['price_open']}")
                print(f"  Comment:    {row['comment']}")
                print(f"  Position:   {row['position_id']}")

    mt5.shutdown()

if __name__ == "__main__":
    search_anywhere()
