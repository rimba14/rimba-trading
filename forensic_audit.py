import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def run_forensic_audit():
    if not mt5.initialize():
        print("MT5 Init failed")
        return
        
    # Analyze last 12 hours
    from_date = datetime.now() - timedelta(hours=12)
    to_date = datetime.now()
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        print("No trades found in the last 12 hours.")
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    # Filter for closing deals (entry == 1)
    df_closes = df[df['entry'] == 1].copy()
    
    if df_closes.empty:
        print("No closed trades found.")
        return
        
    print(f"\n--- FORENSIC AUDIT ({len(df_closes)} TRADES) ---")
    total_pnl = df_closes['profit'].sum()
    print(f"Total PnL: ${total_pnl:.2f}")
    
    # Analyze by Reason
    # 3 = Client (Manual/Expert), 4 = SL, 5 = TP
    print("\n[REASONS]")
    print(df_closes['reason'].value_counts().rename({3: 'EXPERT', 4: 'SL', 5: 'TP'}))
    
    # Analyze by Symbol
    print("\n[SYMBOLS]")
    print(df_closes.groupby('symbol')['profit'].sum().sort_values())
    
    # Calculate Avg Duration
    # d.time is timestamp, we need to find the opening deal for each
    durations = []
    for idx, d in df_closes.iterrows():
        # find matching entry deal
        entry_deal = df[(df['symbol'] == d['symbol']) & (df['position_id'] == d['position_id']) & (df['entry'] == 0)]
        if not entry_deal.empty:
            duration = d['time'] - entry_deal.iloc[0]['time']
            durations.append(duration / 60) # mins
            
    if durations:
        print(f"\nAvg Trade Duration: {sum(durations)/len(durations):.1f} mins")

if __name__ == "__main__":
    run_forensic_audit()
