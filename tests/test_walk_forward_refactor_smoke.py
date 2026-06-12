import sys
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

def test_walk_forward_backtest_refactor():
    # Mock MetaTrader5 before importing walk_forward_backtest
    sys.modules['MetaTrader5'] = MagicMock()

    import walk_forward_backtest
    from walk_forward_backtest import BacktestConfig, simulate_oos_trading

    # Create a dummy test_df
    idx = pd.date_range(start="2026-01-01", periods=10, freq="1h")
    test_df = pd.DataFrame({
        "close": np.linspace(1.1000, 1.1100, 10),
        "spread": np.ones(10) * 10
    }, index=idx)

    # Dummy probs
    probs = np.array([0.6, 0.6, 0.4, 0.4, 0.5, 0.5, 0.6, 0.4, 0.5, 0.5])

    # Test with default config
    pnl, log = simulate_oos_trading(test_df, probs)
    assert isinstance(pnl, list)
    assert isinstance(log, list)

    # Test with custom config
    config = BacktestConfig(flat_commission=1.0, swap_charge=2.0)
    pnl_custom, log_custom = simulate_oos_trading(test_df, probs, config=config)
    assert isinstance(pnl_custom, list)

    # Verify config was used (this is a bit indirect without deep inspection,
    # but the fact it runs without error is good)
    print("Smoke test passed!")

if __name__ == "__main__":
    test_walk_forward_backtest_refactor()
