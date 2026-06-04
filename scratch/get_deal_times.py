import sys
import os
import pandas as pd
from datetime import datetime

sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    ticket = 1322005892
    from_date = datetime(2026, 5, 1)
    to_date = datetime.now()
    
    deals = mt5.history_deals_get(from_date, to_date)
    if deals:
        df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        match_deals = df_deals[df_deals['position_id'] == ticket]
        for idx, row in match_deals.iterrows():
            print(f"Deal Ticket: {row['ticket']}")
            print(f"  Time: {datetime.fromtimestamp(row['time'])}")
            print(f"  Symbol: {row['symbol']}")
            print(f"  Type: {'BUY' if row['type'] == 0 else 'SELL'}")
            print(f"  Entry: {'IN' if row['entry'] == 0 else 'OUT'}")
            print(f"  Volume: {row['volume']}")
            print(f"  Price: {row['price']}")
            print(f"  Profit: {row['profit']}")
            print(f"  Comment: {row['comment']}")
            print("-" * 40)
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
