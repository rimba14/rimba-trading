import pandas as pd
import numpy as np
from datetime import datetime
from qf_lib.common.enums.frequency import Frequency
from qf_lib.common.tickers.tickers import BloombergTicker
from qf_lib.containers.qf_data_array import QFDataArray
from vantage_execute import SentinelConductor

# Sentinel v13.5 — QF-Lib Adapter
# Bridges the 5-Layer Linear Pipeline with the QF Event-Driven Backtester

class SentinelQFAdapter:
    def __init__(self):
        print("[QF_ADAPTER] Initializing Sentinel Conductor for Backtest Mode...")
        self.conductor = SentinelConductor()
        self.cognition_factor = 0.5 # Baseline

    def simulate_ohlcv_streaming(self, symbol, full_df):
        """
        Simulates an event-driven stream by passing windows of 
        increasing size to the Sentinel Conductor.
        """
        print(f"[QF_ADAPTER] Starting Backtest for {symbol} | Data Length: {len(full_df)}")
        results = []
        
        # Minimum window required for DWT (Layer 1) is ~256 bars
        min_window = 256
        if len(full_df) <= min_window:
            print("[QF_ADAPTER] ERROR: Not enough data for backtest.")
            return []

        for i in range(min_window, len(full_df)):
            window = full_df.iloc[:i] 
            
            # Layer 1-5 Execution
            try:
                action, context = self.conductor.run_one_cycle(symbol, window, self.cognition_factor)
                results.append({
                    "time": window.index[-1],
                    "action": action['action'],
                    "sl": action.get('sl', 0),
                    "tp": action.get('tp', 0),
                    "sentiment": context.get('cognition_factor', 0)
                })
            except Exception as e:
                print(f"[QF_ADAPTER] Cycle failure at {window.index[-1]}: {e}")
                
        return pd.DataFrame(results)

if __name__ == "__main__":
    print("--- SENTINEL QF-LIB BACKTEST ADAPTER ---")
    
    # 1. Create dummy historical data
    times = pd.date_range("2025-01-01", periods=300, freq='15min')
    data = {
        'open': np.random.randn(300).cumsum() + 100,
        'high': np.random.randn(300).cumsum() + 101,
        'low': np.random.randn(300).cumsum() + 99,
        'close': np.random.randn(300).cumsum() + 100,
        'tick_volume': np.random.randint(100, 1000, 300)
    }
    mock_df = pd.DataFrame(data, index=times)
    
    # 2. Run Adapter
    adapter = SentinelQFAdapter()
    bt_results = adapter.simulate_ohlcv_streaming("BACKTEST_MOCK", mock_df)
    
    if not bt_results.empty:
        print("\n[BACKTEST COMPLETE]")
        print(bt_results.tail(5))
        print(f"\nFinal Actions Logged: {len(bt_results)}")
    else:
        print("\n[BACKTEST FAILED]")
