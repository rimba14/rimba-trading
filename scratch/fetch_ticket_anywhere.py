import MetaTrader5 as mt5
from datetime import datetime, timezone
import pandas as pd

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
        
    val = 1322005892
    from_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    to_date = datetime.now(timezone.utc)
    
    print(f"=== SEARCHING MT5 FOR {val} ===")
    
    deals = mt5.history_deals_get(from_date, to_date)
    if deals:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        # check each column for match
        match = df[(df == val).any(axis=1)]
        if not match.empty:
            print("\nFound in history deals:")
            print(match.to_string())
            
    orders = mt5.history_orders_get(from_date, to_date)
    if orders:
        df_ord = pd.DataFrame(list(orders), columns=orders[0]._asdict().keys())
        match_ord = df_ord[(df_ord == val).any(axis=1)]
        if not match_ord.empty:
            print("\nFound in history orders:")
            print(match_ord.to_string())
            
    # Check open positions
    open_pos = mt5.positions_get()
    if open_pos:
        df_pos = pd.DataFrame(list(open_pos), columns=open_pos[0]._asdict().keys())
        match_pos = df_pos[(df_pos == val).any(axis=1)]
        if not match_pos.empty:
            print("\nFound in open positions:")
            print(match_pos.to_string())
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
