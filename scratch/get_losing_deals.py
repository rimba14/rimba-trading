import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import pandas as pd

def run_target_isolation():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    now = datetime.now(timezone.utc)
    from_date = now - timedelta(hours=48)
    
    deals = mt5.history_deals_get(from_date, now)
    if not deals:
        print("No deals found in the last 48 hours.")
        mt5.shutdown()
        return

    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter for losing round-trip exits
    exits = df[(df['entry'] == mt5.DEAL_ENTRY_OUT) & (df['profit'] < 0)].copy()
    exits.sort_values('time', ascending=False, inplace=True)
    
    print(f"Total losing exits found in last 48h: {len(exits)}")
    
    targets = exits.head(3)
    
    print("\n=== 3 MOST RECENT LOSING ROUND-TRIP TRADES ===")
    for idx, row in targets.iterrows():
        pos_id = row['position_id']
        # Find corresponding entry deal
        entries = df[(df['position_id'] == pos_id) & (df['entry'] == mt5.DEAL_ENTRY_IN)]
        time_in = "N/A"
        price_in = 0.0
        if not entries.empty:
            entry_deal = entries.iloc[0]
            time_in = datetime.fromtimestamp(entry_deal['time'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            price_in = entry_deal['price']
            
        time_out = datetime.fromtimestamp(row['time'], timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        print(f"\nTarget Ticket (Exit Deal): {row['ticket']} | Position ID: {pos_id}")
        print(f"Symbol:     {row['symbol']}")
        print(f"Time In:    {time_in} (Raw: {int(entries.iloc[0]['time']) if not entries.empty else 'N/A'})")
        print(f"Time Out:   {time_out} (Raw: {int(row['time'])})")
        print(f"Price In:   {price_in:.5f}")
        print(f"Price Out:  {row['price']:.5f}")
        print(f"Profit:     {row['profit']:.2f}")
        print(f"Comment:    {row['comment']}")

    mt5.shutdown()

if __name__ == "__main__":
    run_target_isolation()
