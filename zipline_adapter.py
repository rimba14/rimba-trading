import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import os
from datetime import datetime, timezone

def export_mt5_to_zipline(symbol, timeframe=mt5.TIMEFRAME_D1, count=1000):
    """
    Exports MT5 history to a Zipline-compatible CSV format on the E: drive.
    Zipline CSV requirement: [date, open, high, low, close, volume, dividend, split]
    """
    if not mt5.initialize():
        print("MT5 initialize failed")
        return

    print(f"[INGEST] Exporting {symbol} from MT5...")
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        print(f"Failed to copy rates for {symbol}")
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Rename for Zipline CSV bundle
    df = df.rename(columns={
        'time': 'date',
        'real_volume': 'volume'
    })
    
    # Required Zipline columns
    df['dividend'] = 0.0
    df['split'] = 1.0
    
    # Selection
    df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'dividend', 'split']]
    
    # Storage on E: drive
    export_dir = "C:\\Sentinel_Project\\zipline_data/csv_ingest"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
        
    csv_path = os.path.join(export_dir, f"{symbol}.csv")
    df.to_csv(csv_path, index=False)
    print(f"[INGEST] Saved {symbol} to {csv_path}")
    
    # Zipline requires a metadata file or specific folder structure
    # This script facilitates the creation of the csvdir bundle
    return csv_path

if __name__ == "__main__":
    # Test with major assets from the 49-asset watchlist
    targets = ['EURUSD', 'USDJPY', 'GBPUSD', 'NAS100', 'XAUUSD', 'BTCUSD']
    for sym in targets:
        export_mt5_to_zipline(sym)
    
    print("\n[INGEST] MT5 Batch Export Complete.")
    print("Action Required: Run 'zipline ingest -b csvdir' with C:\\Sentinel_Project\\zipline_data/csv_ingest as the source.")
