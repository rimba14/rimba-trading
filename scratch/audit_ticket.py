import sys
import os
import pandas as pd
from datetime import datetime, timedelta

sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    ticket = 1322005892
    print(f"Searching for ticket {ticket} in history...")
    
    # Check history deals
    from_date = datetime.now() - timedelta(days=30)
    to_date = datetime.now() + timedelta(days=1)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if deals:
        df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        match_deal = df_deals[(df_deals['position_id'] == ticket) | (df_deals['ticket'] == ticket)]
        if not match_deal.empty:
            print("\n=== MATCHING DEALS ===")
            print(match_deal[['ticket', 'position_id', 'symbol', 'type', 'entry', 'volume', 'price', 'profit', 'comment']].to_string())
        else:
            print("No matching deals found for ticket in last 30 days.")
    else:
        print("No history deals retrieved.")

    # Let's list the last 5 closed losing trades if ticket search failed or to provide context
    if deals:
        df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        # Filter out balance operations (type 2) and only look at deals with entry = 1 (out) and profit < 0
        closed_losing = df_deals[(df_deals['entry'] == 1) & (df_deals['profit'] < 0)].sort_values('time', ascending=False)
        print("\n=== RECENT CLOSED LOSING DEALS ===")
        print(closed_losing[['time', 'ticket', 'position_id', 'symbol', 'type', 'volume', 'price', 'profit', 'comment']].head(10).to_string())

    mt5.shutdown()

if __name__ == "__main__":
    main()
