import pandas as pd
import numpy as np
import os
import vectorbt as vbt

class VBTAdapter:
    def __init__(self, data_dir="C:\\Sentinel_Project\\zipline_data/csv_ingest"):
        self.data_dir = data_dir
        
    def load_symbol(self, symbol):
        """Loads a MetaTrader 5 CSV export into a VectorBT-ready DataFrame."""
        path = os.path.join(self.data_dir, f"{symbol}.csv")
        if not os.path.exists(path):
            print(f"[VBT] File not found: {path}")
            return None
            
        df = pd.read_csv(path, parse_dates=['date'])
        df = df.set_index('date')
        return df
        
    def get_close_matrix(self, symbols):
        """Creates a concatenated matrix of closing prices for vectorized backtesting."""
        data_frames = {}
        for sym in symbols:
            df = self.load_symbol(sym)
            if df is not None:
                data_frames[sym] = df['close']
                
        return pd.DataFrame(data_frames)

if __name__ == "__main__":
    adapter = VBTAdapter()
    major_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'NAS100', 'BTCUSD']
    closes = adapter.get_close_matrix(major_symbols)
    
    if not closes.empty:
        print(f"[VBT] Loaded closure matrix for {len(closes.columns)} assets.")
        print(closes.tail(5))
        
        # Quick check: 20/50 SMA Crossover simulation
        fast_ma = vbt.MA.run(closes, 20)
        slow_ma = vbt.MA.run(closes, 50)
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)
        
        portfolio = vbt.Portfolio.from_signals(closes, entries, exits, freq='1D')
        print(f"\n[VBT] Sample Backtest Result (Annualized Return):")
        print(portfolio.annualized_return())
