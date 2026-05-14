import sys
sys.path.append("C:/Sentinel_Project")
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, timezone

def fetch_recent_deals():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return
        
    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(days=2)
    deals = mt5.history_deals_get(from_dt, now)
    
    if not deals:
        print("No deals found.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    closed = df[df['entry'] == mt5.DEAL_ENTRY_OUT]
    if not closed.empty:
        closed = closed.sort_values(by='time', ascending=False)
        with open("C:/Sentinel_Project/scratch/level7_deals.txt", "w") as f:
            f.write("=== Last 5 Closed Deals ===\n")
            for idx, row in closed.head(5).iterrows():
                pos_id = row['position_id']
                in_deals = df[(df['position_id'] == pos_id) & (df['entry'] == mt5.DEAL_ENTRY_IN)]
                time_in = in_deals['time'].iloc[0] if not in_deals.empty else "N/A"
                price_in = in_deals['price'].iloc[0] if not in_deals.empty else "N/A"
                f.write(f"ExitTicket: {row['ticket']} | PosID (EntryTicket): {pos_id} | Symbol: {row['symbol']} | Time In: {time_in} | Time Out: {row['time']} | Price In: {price_in} | Price Out: {row['price']} | Profit: {row['profit']} | Comment: {row['comment']}\n")
        print("Saved to C:/Sentinel_Project/scratch/level7_deals.txt")
            
    mt5.shutdown()

if __name__ == "__main__":
    fetch_recent_deals()
