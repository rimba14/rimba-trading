import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def get_positions_update():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return

    account = mt5.account_info()
    if account:
        print(f"--- ACCOUNT SUMMARY ---")
        print(f"Balance: ${account.balance:,.2f}")
        print(f"Equity:  ${account.equity:,.2f}")
        print(f"Profit:  ${account.profit:,.2f}")
        print(f"Margin:  ${account.margin_level:.2f}%")
        print("-" * 30)

    positions = mt5.positions_get()
    if positions is None:
        print("No active positions.")
    elif len(positions) == 0:
        print("No active positions.")
    else:
        df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Select relevant columns for the user
        display_cols = ['symbol', 'type', 'volume', 'price_open', 'price_current', 'sl', 'tp', 'profit']
        # Map type to BUY/SELL
        df['type'] = df['type'].map({0: 'BUY', 1: 'SELL'})
        
        print(f"\n--- ACTIVE POSITIONS ({len(positions)}) ---")
        print(df[display_cols].to_string(index=False))
        
        total_profit = df['profit'].sum()
        print(f"\nTotal Floating P/L: ${total_profit:,.2f}")

    mt5.shutdown()

if __name__ == "__main__":
    get_positions_update()
