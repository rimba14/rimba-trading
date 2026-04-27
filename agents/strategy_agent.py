"""
strategy_agent.py - STRATEGY EXECUTOR
Monitors charts and executes technical strategy signals.
"""

import nice_funcs_hyperliquid as n
import strategies.bb_squeeze_adx as strat
import time

class StrategyAgent:
    def __init__(self, symbol, interval, account_obj):
        self.symbol = symbol
        self.interval = interval
        self.account = account_obj

    def run(self):
        """Executes one cycle of the strategy."""
        print(f"[STRATEGY] Scanning {self.symbol} ({self.interval})...")
        
        # 1. Fetch data
        df = n.get_ohlcv(self.symbol, self.interval, 50) # Last 50 candles
        if df.empty:
            print(f"[STRATEGY] No data found for {self.symbol}.")
            return None, None

        # 2. Calculate Indicators
        df = strat.calculate_indicators(df)
        
        # 3. Check for Signals
        long_sig, short_sig = strat.get_signals(df)
        
        if long_sig:
            print(f"[STRATEGY] LONG Signal detected for {self.symbol}!")
            return "BUY", "BB Squeeze Breakout (Long)"
        elif short_sig:
            print(f"[STRATEGY] SHORT Signal detected for {self.symbol}!")
            return "SELL", "BB Squeeze Breakout (Short)"
        
        return "HOLD", "No squeeze release detected."

if __name__ == "__main__":
    # Test (requires account_obj)
    pass
