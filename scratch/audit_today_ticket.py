import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import pandas as pd

def audit_today():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    # Set range from yesterday to now to capture today's deals perfectly
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=2)
    
    deals = mt5.history_deals_get(from_date, now)
    if not deals:
        print("No deals found in the last 2 days.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    target_deals = df[df['position_id'] == 1314684045]
    
    if target_deals.empty:
        # Check by ticket
        target_deals = df[df['ticket'] == 1314684045]
        
    if target_deals.empty:
        print("Ticket 1314684045 not found in MT5 deal history database yet (possibly cached or pending terminal write).")
    else:
        print(f"=== FOUND TODAY'S DEAL FORENSICS FOR TICKET 1314684045 ===")
        for idx, row in target_deals.iterrows():
            d_time = datetime.fromtimestamp(row['time'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            role = "ENTRY (IN)" if row['entry'] == mt5.DEAL_ENTRY_IN else ("EXIT (OUT)" if row['entry'] == mt5.DEAL_ENTRY_OUT else "IN/OUT")
            print(f"\nDeal Ticket: {row['ticket']} | {role}")
            print(f"  Symbol:    {row['symbol']}")
            print(f"  Time:      {d_time}")
            print(f"  Type:      {'BUY' if row['type'] == mt5.ORDER_TYPE_BUY else 'SELL'}")
            print(f"  Volume:    {row['volume']}")
            print(f"  Price:     {row['price']:.5f}")
            print(f"  Profit:    {row['profit']:.2f} USD")
            print(f"  Comment:   {row['comment']}")
            print(f"  Position:  {row['position_id']}")
            
    mt5.shutdown()

if __name__ == "__main__":
    audit_today()
