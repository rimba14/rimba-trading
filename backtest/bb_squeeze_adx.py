"""
backtest/bb_squeeze_adx.py - STRATEGY VALIDATION
Runs historical backtests for the BB Squeeze ADX strategy.
"""

import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
import sys
import os

# Add parent directory to path to import strategies
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from strategies.bb_squeeze_adx import calculate_indicators

class BBSqueezeADX(Strategy):
    bb_window = 20
    bb_std = 2.0
    keltner_window = 20
    keltner_atr_mult = 1.5
    adx_period = 14
    adx_threshold = 25
    take_profit = 0.05
    stop_loss = 0.03

    def init(self):
        # We access the columns directly
        self.squeeze_on = self.I(lambda x: x, self.data.Squeeze_on.astype(float))
        self.adx = self.I(lambda x: x, self.data.Adx)
        self.bb_upper = self.I(lambda x: x, self.data.Bb_upper)
        self.bb_lower = self.I(lambda x: x, self.data.Bb_lower)

    def next(self):
        if len(self.data) < 2:
            return

        # Squeeze Release: Prev ON, Current OFF
        squeeze_released = self.squeeze_on[-2] == 1.0 and self.squeeze_on[-1] == 0.0
        trending = self.adx[-1] > self.adx_threshold

        if squeeze_released and trending:
            price = self.data.Close[-1]
            if price > self.bb_upper[-1] and not self.position:
                sl = price * (1 - self.stop_loss)
                tp = price * (1 + self.take_profit)
                self.buy(sl=sl, tp=tp)
            elif price < self.bb_lower[-1] and not self.position:
                sl = price * (1 + self.stop_loss)
                tp = price * (1 - self.stop_loss)
                self.sell(sl=sl, tp=tp)

if __name__ == "__main__":
    import nice_funcs_hyperliquid as n
    print("Fetching historical data for backtest...")
    data = n.get_ohlcv("BTC", "4h", 100) 
    
    if data.empty:
        print("No data found. Backtest aborted.")
    else:
        print("Calculating indicators...")
        data = calculate_indicators(data)
        data.columns = [c.capitalize() for c in data.columns]
        data = data.dropna()

        if data.empty:
            print("Data is empty after dropna! Check indicator windows.")
        else:
            print("Running backtest engine...")
            bt = Backtest(data, BBSqueezeADX, cash=100_000, commission=0.002)
            stats = bt.run()
            print("\n" + "="*30)
            print("BACKTEST RESULTS")
            print("="*30)
            print(stats)
