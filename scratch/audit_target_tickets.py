import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import pandas as pd
import json

def audit():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    target_positions = [1306172614, 1303723015, 1306704393, 1314684045]
    
    # Query deals in the last 60 days to capture these tickets
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=60)
    
    deals = mt5.history_deals_get(from_date, now)
    if not deals:
        print("No deals found in the last 60 days.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    print("=== TARGET ISOLATION QUERY ===")
    for pos_id in target_positions:
        pos_deals = df[df['position_id'] == pos_id]
        if pos_deals.empty:
            # Let's check if the ticket number matches the ticket instead of position_id
            pos_deals = df[df['ticket'] == pos_id]
            if pos_deals.empty:
                print(f"\nTarget Ticket/Position {pos_id}: Not found in 60-day history.")
                continue
                
        print(f"\n--- Forensics for Target ID: {pos_id} ---")
        for idx, row in pos_deals.iterrows():
            d_time = datetime.fromtimestamp(row['time'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            role = "ENTRY (IN)" if row['entry'] == mt5.DEAL_ENTRY_IN else ("EXIT (OUT)" if row['entry'] == mt5.DEAL_ENTRY_OUT else "IN/OUT")
            print(f"Deal Ticket: {row['ticket']} | {role}")
            print(f"  Symbol:    {row['symbol']}")
            print(f"  Time:      {d_time} (Raw: {int(row['time'])})")
            print(f"  Type:      {'BUY' if row['type'] == mt5.ORDER_TYPE_BUY else 'SELL'}")
            print(f"  Volume:    {row['volume']}")
            print(f"  Price:     {row['price']:.5f}")
            print(f"  Profit:    {row['profit']:.2f} USD")
            print(f"  Comment:   {row['comment']}")
            print(f"  Magic:     {row['magic']}")
            
    mt5.shutdown()

if __name__ == "__main__":
    audit()
