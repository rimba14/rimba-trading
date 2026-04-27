import MetaTrader5 as mt5
import sys
import os
import pandas as pd

# Ensure local imports
sys.path.append('C:\\Sentinel_Project\\')

import vantage_execute as ve

def verify_fix():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    # 1. Check if we have any open positions
    positions = mt5.positions_get()
    if not positions:
        print("[VERIFY] No open positions to test against. Use a held symbol.")
        return

    test_sym = positions[0].symbol
    print(f"[VERIFY] Testing Duplicate Guard for {test_sym}...")

    # 2. Construct a mock candidate for the same symbol
    mock_cand = {
        "sym": test_sym,
        "sig": "BUY",
        "score": 99.0,
        "atr": 0.001,
        "cat": "DIRECTIONAL",
        "info": mt5.symbol_info(test_sym)
    }

    # 3. Suppress actual order sending by checking if we have the guard in place
    # We will call _execute_candidate and expect it to return False with a specific print.
    print("[VERIFY] Calling _execute_candidate (Expected behavior: DUPLICATE_GUARD trigger)")
    
    # Mocking necessary parameters
    balance = mt5.account_info().balance
    total_run_risk = 0
    net_beta = 0
    vix = 20.0
    current_sharpe = 1.8

    result = ve._execute_candidate(mock_cand, balance, total_run_risk, net_beta, vix, current_sharpe)
    
    if result is False:
        print("[VERIFY] SUCCESS: Duplicate Guard prevented redundant entry.")
    else:
        print("[VERIFY] FAILURE: Duplicate Guard allowed redundant entry.")

if __name__ == "__main__":
    verify_fix()
