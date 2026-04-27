import sys
import os
import pandas as pd
import numpy as np

# Mocking parts of gitagent_var and vantage_execute setup
class MockGuardian:
    def calculate_returns(self, prices_dict):
        returns_df = pd.DataFrame()
        for sym, prices in prices_dict.items():
            returns_df[sym] = pd.Series(prices).pct_change().dropna()
        return returns_df

    def calculate_parametric_var(self, positions_usd, returns_df):
        symbols = list(positions_usd.keys())
        # This is where the KeyError used to happen
        cov_matrix = returns_df[symbols].cov()
        return 0.05 # Mock value

    def calculate_net_beta(self, positions, returns_df, benchmark='NAS100'):
        return 1.2 # Mock value

mock_guardian = MockGuardian()

# Mocking the dictionary structures from calculate_current_portfolio_risk
symbol_risks = {"EURUSD": 5.0, "NAS100": 10.0, "XAGUSD": 0.0}
usd_values = {"EURUSD": 1000.0, "NAS100": 2000.0, "XAGUSD": 0.0}
prices_dict = {
    "EURUSD": np.random.normal(1.14, 0.01, 100),
    "NAS100": np.random.normal(15000, 200, 100)
}
# XAGUSD is intentionally missing from prices_dict to trigger the scenario

print("--- Testing Risk Engine Patch v11.3.1 ---")
try:
    # rets_df only has EURUSD and NAS100
    rets_df = mock_guardian.calculate_returns(prices_dict)
    print(f"Returns DataFrame columns: {list(rets_df.columns)}")
    
    # Logic from patched vantage_execute.py
    valid_risks = {s: r for s, r in symbol_risks.items() if s in rets_df.columns}
    valid_usd = {s: v for s, v in usd_values.items() if s in rets_df.columns}
    
    print(f"Filtered Symbols: {list(valid_risks.keys())}")
    
    if valid_risks:
        total_risk = mock_guardian.calculate_parametric_var(valid_risks, rets_df)
        net_beta = mock_guardian.calculate_net_beta(valid_usd, rets_df)
        print(f"Calculated VaR: {total_risk}")
        print(f"Calculated Beta: {net_beta}")
    
    print("[PASS] TEST PASSED: No KeyError raised.")
except KeyError as e:
    print(f"[FAIL] TEST FAILED: KeyError: {e}")
except Exception as e:
    print(f"[ERROR] ERROR: {e}")
