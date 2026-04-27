import pandas as pd
import os

class BacktestingAdapter:
    """
    Adapter to load MT5 historical CSVs into Backtesting.py compatible DataFrames.
    Required format: Index=Datetime, columns=['Open', 'High', 'Low', 'Close', 'Volume']
    """
    def __init__(self, data_dir="C:\\Sentinel_Project\\zipline_data/csv_ingest"):
        self.data_dir = data_dir

    def load_data(self, symbol):
        path = os.path.join(self.data_dir, f"{symbol}.csv")
        if not os.path.exists(path):
            print(f"[LOADER] Error: {path} not found.")
            return None
            
        # Zipline format was [date, open, high, low, close, volume, dividend, split]
        df = pd.read_csv(path, parse_dates=['date'])
        
        # Format for Backtesting.py (Capitalized OHLCV)
        df = df.rename(columns={
            'date': 'Date',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })
        
        df = df.set_index('Date')
        
        # Sort index to ensure temporal order
        df = df.sort_index()
        
        # Drop unwanted columns
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        
        print(f"[LOADER] {symbol} loaded: {len(df)} bars.")
        return df

if __name__ == "__main__":
    loader = BacktestingAdapter()
    test_df = loader.load_data("EURUSD")
    if test_df is not None:
        print(test_df.head(2))
