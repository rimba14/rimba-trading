"""
test_v3096_verification.py
Tests version handshake validation and ATR risk distance floor.
"""
import os
import sys
import shutil
import pytest
from unittest import mock

# sys.path.insert(0, r"C:\Sentinel_Project")
# os.chdir(r"C:\Sentinel_Project")

from unittest.mock import MagicMock
import sys
# Mock MetaTrader5 before importing pre_execution_gate
sys.modules["MetaTrader5"] = MagicMock()

import pre_execution_gate as peg
from pre_execution_gate import GateContext
import sentinel_config as cfg
import MetaTrader5 as mt5

def test_verify_code_coherence():
    from execute_live_top5 import verify_code_coherence
    git_hash = verify_code_coherence()
    assert isinstance(git_hash, str)
    assert len(git_hash) > 0

def test_version_handshake_mismatch():
    # Test that mismatches raise a hard termination
    # We will backup active_git_hash.txt if it exists
    hash_file = "C:/Sentinel_Project/data/active_git_hash.txt"
    backup_file = "C:/Sentinel_Project/data/active_git_hash.txt.bak"
    
    has_backup = False
    if os.path.exists(hash_file):
        shutil.copy2(hash_file, backup_file)
        has_backup = True
        
    try:
        # Write a dummy mismatched hash
        with open(hash_file, "w") as f:
            f.write("DUMMY_MISMATCHED_HASH_123456")
            
        # Run a subprocess execution of execute_live_top5.py and verify it exits with the CRITICAL_VERSION_DRIFT_TERMINATION error
        import subprocess
        res = subprocess.run([sys.executable, "execute_live_top5.py"], capture_output=True, text=True)
        assert "[CRITICAL_VERSION_DRIFT_TERMINATION]" in res.stdout or "[CRITICAL_VERSION_DRIFT_TERMINATION]" in res.stderr
        assert res.returncode != 0
        print("[OK] Mismatched version signature successfully blocked process execution.")
        
    finally:
        # Restore backup
        if os.path.exists(hash_file):
            os.remove(hash_file)
        if has_backup:
            shutil.move(backup_file, hash_file)

def test_atr_floor_rejection():
    # Setup test inputs for pre_execution_gate.run_all_gates
    # We will mock mt5.copy_rates_from_pos to return specific prices that produce a known ATR.
    # ATR = Sum(max(high-low, abs(high-prev_close), abs(low-prev_close))) / 19
    # Let's say High=1.1010, Low=1.1000, Close=1.1005, prev_Close=1.1005
    # True range = 0.0010
    # Thus ATR = 0.0010. 
    # Minimum allowed distance = 3.5 * ATR = 0.0035
    # If we pass sl_distance = 0.0020 (< 0.0035), it should fail.
    # If we pass sl_distance = 0.0040 (>= 0.0035), it should pass.
    
    mock_rates = []
    # 20 elements
    for i in range(20):
        # time, open, high, low, close, tick_volume, spread, real_volume
        mock_rates.append((0, 1.1005, 1.1010, 1.1000, 1.1005, 100, 0, 100))
        
    import numpy as np
    mock_rates_arr = np.array(mock_rates, dtype=[
        ('time', '<i8'), ('open', '<f8'), ('high', '<f8'), ('low', '<f8'),
        ('close', '<f8'), ('tick_volume', '<i8'), ('spread', '<i8'), ('real_volume', '<i8')
    ])
    
    with mock.patch("pre_execution_gate.mt5.copy_rates_from_pos", return_value=mock_rates_arr) as mock_rates_func, \
         mock.patch("pre_execution_gate.mt5.initialize", return_value=True), \
         mock.patch("pre_execution_gate.mt5.positions_get", return_value=[]), \
         mock.patch("pre_execution_gate.mt5.orders_get", return_value=[]), \
         mock.patch("pre_execution_gate.mt5.symbol_info", return_value=mock.Mock(trade_contract_size=100000.0)):
        
        # Test Case 1: SL distance 0.0020 (< 3.5 * ATR) -> Should fail
        ctx_fail = GateContext(
            symbol="EURUSD", direction="BUY", asset_class="FOREX",
            regime="BULL", kelly_lots=0.01,
            entry_price=1.1000, sl_distance=0.0020, tp_distance=0.0050,
            risk_usd=10.0, equity=1000.0, current_heat_usd=50.0,
            embargo_registry={}
        )
        verdict_fail = peg.run_all_gates(ctx_fail, ticket_ref="TEST_123")
        assert not verdict_fail.approved
        assert "falls below ATR Floor" in verdict_fail.summary()
        print("[OK] ATR Floor check successfully rejected non-compliant Stop Loss.")

        # Test Case 2: SL distance 0.0040 (>= 3.5 * ATR) -> Should pass
        ctx_pass = GateContext(
            symbol="EURUSD", direction="BUY", asset_class="FOREX",
            regime="BULL", kelly_lots=0.01,
            entry_price=1.1000, sl_distance=0.0040, tp_distance=0.0100,
            risk_usd=10.0, equity=1000.0, current_heat_usd=50.0,
            embargo_registry={}
        )
        verdict_pass = peg.run_all_gates(ctx_pass, ticket_ref="TEST_456")
        assert verdict_pass.approved
        print("[OK] Compliance verification passed for valid Stop Loss.")

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", __file__]))
