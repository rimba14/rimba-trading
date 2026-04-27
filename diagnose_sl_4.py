import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def run_deep_audit():
    if not mt5.initialize():
        print("MT5 Init failed")
        return
        
    # Analyze last 1 hour (since the Sl fix)
    from_date = datetime.now() - timedelta(hours=1)
    to_date = datetime.now()
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        print("No trades found in the last 1 hour.")
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # We want to see deals that have profit/loss or specify SL
    print(f"\n--- DEALS IN LAST HOUR ({len(df)} TOTAL DEALS) ---")
    
    if len(df) > 0:
        for idx, row in df.iterrows():
            print(f"{row['time']}: {row['symbol']} Type:{row['type']} Vol:{row['volume']} Price:{row['price']} Profit:{row['profit']} Reason:{row['reason']}")
            
if __name__ == "__main__":
    run_deep_audit()
