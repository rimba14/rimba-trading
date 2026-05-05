import MetaTrader5 as mt5
import pandas as pd
import json

def get_mt5_positions():
    if not mt5.initialize():
        print(f"FAILED MT5 initialization failed, error code: {mt5.last_error()}")
        return
    
    positions = mt5.positions_get()
    if positions is None:
        print("INFO No positions found on MT5.")
    elif len(positions) == 0:
        print("INFO No open positions.")
    else:
        df = pd.DataFrame([p._asdict() for p in positions])
        # Clean up for display
        cols_to_keep = ['ticket', 'symbol', 'type', 'volume', 'price_open', 'price_current', 'profit', 'sl', 'tp']
        df_clean = df[cols_to_keep]
        
        # Add type description
        df_clean['type_desc'] = df_clean['type'].apply(lambda x: 'BUY' if x == 0 else 'SELL')
        
        print("--- MT5 OPEN POSITIONS ---")
        print(df_clean.to_string(index=False))
        
        total_profit = df_clean['profit'].sum()
        print(f"\nTOTAL NET PROFIT: ${total_profit:.2f}")

    mt5.shutdown()

if __name__ == "__main__":
    get_mt5_positions()
