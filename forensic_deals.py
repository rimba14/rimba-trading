import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("MT5 Initialization Failed")
    quit()

# Get deals from the last 24h
from_date = datetime.now() - timedelta(days=1)
deals = mt5.history_deals_get(from_date, datetime.now())

if deals:
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    # Exclude entries (entry=0), only focus on exits (entry=1)
    df_exits = df[df['entry'] == 1].copy()
    
    # Analyze comments
    comment_counts = df_exits['comment'].value_counts()
    print("\nEXIT REASONS (Comments):")
    print(comment_counts)
    
    # Analyze by symbol
    symbol_pnl = df_exits.groupby('symbol')['profit'].sum()
    print("\nPnL BY SYMBOL:")
    print(symbol_pnl.sort_values())
    
    # Check Average Duration
    # Convert 'time' to datetime if needed, but 'deals' often has 'time_msc'
    # Actually 'time' is seconds since epoch
    # We need to find the entry deal for each exit to calculate duration
    print("\nDURATION SKEW CHECK:")
    # (Optional: this is harder without matching tickets, but let's check PnL distribution)
    print(f"Top Profit: {df_exits['profit'].max():.2f}")
    print(f"Worst Loss: {df_exits['profit'].min():.2f}")
    print(f"Mean PnL: {df_exits['profit'].mean():.2f}")

else:
    print("No deals found.")

mt5.shutdown()
