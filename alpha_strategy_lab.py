from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from backtesting.test import SMA
import backtesting_adapter
import os
import pandas as pd

# --- Alpha Scouts Pipeline (151 Strategy Sample) ---
# We will start with a Sample Ensemble (SMA Cross + Momentum)

class AlphaEnsemble(Strategy):
    n1 = 50
    n2 = 200
    
    def init(self):
        # Precompute indicators
        self.sma_fast = self.I(SMA, self.data.Close, self.n1)
        self.sma_slow = self.I(SMA, self.data.Close, self.n2)
        
    def next(self):
        # Strategy 1: Classical Golden Cross
        if crossover(self.sma_fast, self.sma_slow):
            self.buy()
        elif crossover(self.sma_slow, self.sma_fast):
            self.position.close()

def run_alpha_audit(symbol="NAS100"):
    loader = backtesting_adapter.BacktestingAdapter()
    data = loader.load_data(symbol)
    if data is None: return

    print(f"\n[LAB] Running Alpha Audit for {symbol}...")
    
    bt = Backtest(data, AlphaEnsemble, cash=10000, commission=.001, hedging=False, exclusive_orders=True)
    stats = bt.run()
    
    print("-" * 30)
    print(f"SYMBOL: {symbol}")
    print(f"Final Equity: ${stats['Equity Final [$]']:.2f}")
    print(f"Return: {stats['Return [%]']:.2f}%")
    print(f"Sharpe: {stats['Sharpe Ratio']:.2f}")
    print(f"Max Drawdown: {stats['Max. Drawdown [%]']:.2f}%")
    print("-" * 30)
    
    # Save results to E: drive
    report_path = f"C:\\Sentinel_Project\\zipline_data/report_{symbol}.html"
    bt.plot(filename=report_path, open_browser=False)
    print(f"[LAB] Detailed report saved to: {report_path}")
    
    return stats

def run_master_audit(symbols=['EURUSD', 'GBPUSD', 'NAS100', 'BTCUSD', 'XAUUSD']):
    """Returns a dictionary of Sharpe ratios for weighting calibration."""
    master_weights = {}
    for s in symbols:
        try:
            res = run_alpha_audit(s)
            if res is not None:
                # Use Sharpe Ratio as the primary weight (minimum 0.1)
                master_weights[s] = max(0.1, res['Sharpe Ratio'])
        except Exception as e:
            print(f"[LAB_ERR] Failed audit for {s}: {e}")
            
    return master_weights

if __name__ == "__main__":
    weights = run_master_audit()
    print("\n[LAB] MASTER ALPHA AUDIT COMPLETE")
    print(weights)
