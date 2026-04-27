import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def run_deep_audit():
    if not mt5.initialize():
        print("MT5 Init failed")
        return
        
    # Analyze last 4 hours (since hysteresis was added)
    from_date = datetime.now() - timedelta(hours=4)
    to_date = datetime.now()
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        print("No trades found in the last 4 hours.")
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df_closes = df[df['entry'] == 1].copy()
    
    if df_closes.empty:
        print("No closed trades found.")
        return
        
    print(f"\n--- STRUCTURAL AUDIT ({len(df_closes)} TRADES) ---")
    total_pnl = df_closes['profit'].sum()
    print(f"Total PnL: ${total_pnl:.2f}")
    
    # Analyze by Reason
    print("\n[REASONS]")
    print(df_closes['reason'].value_counts().rename({3: 'EXPERT', 4: 'SL', 5: 'TP'}))
    
    print("\n[SYMBOLS AND PNL]")
    sym_grouped = df_closes.groupby('symbol')['profit'].agg(['sum', 'count'])
    print(sym_grouped.sort_values('sum'))

    # Let's see the average PnL of SL vs EXPERT vs TP
    print("\n[AVG PNL BY REASON]")
    print(df_closes.groupby('reason')['profit'].mean().rename({3: 'EXPERT', 4: 'SL', 5: 'TP'}))

if __name__ == "__main__":
    run_deep_audit()
