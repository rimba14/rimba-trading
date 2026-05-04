import MetaTrader5 as mt5
import pandas as pd
import os

def get_positions():
    if not mt5.initialize():
        print("MT5 initialization failed")
        return None
    
    positions = mt5.positions_get()
    if positions is None:
        print("No positions found or error")
        mt5.shutdown()
        return None
    
    if len(positions) == 0:
        print("No open positions.")
        mt5.shutdown()
        return []

    df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    mt5.shutdown()
    return df

if __name__ == "__main__":
    pos_df = get_positions()
    if isinstance(pos_df, pd.DataFrame) and not pos_df.empty:
        print(pos_df[['ticket', 'symbol', 'type', 'volume', 'price_open', 'price_current', 'profit']].to_string())
    elif pos_df == []:
        pass
