import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, mock_open
from gitagent_native_validator import NativeSentinelValidator

@pytest.fixture
def validator():
    return NativeSentinelValidator()

def generate_vol_df(vol, length=100, seed=42):
    # Returns are approx normal(0, vol)
    np.random.seed(seed)
    returns = np.random.normal(0, vol, length)
    prices = np.exp(np.cumsum(returns))
    return pd.DataFrame({"close": prices})

def test_calculate_drift(validator):
    assert validator.calculate_drift(0, 0.0012) == 0.0
    assert validator.calculate_drift(0.0012, 0.0012) == 0.0
    assert pytest.approx(validator.calculate_drift(0.0012, 0.00156)) == 0.3
    assert pytest.approx(validator.calculate_drift(0.0012, 0.00084)) == 0.3

@patch("builtins.open", new_callable=mock_open)
def test_generate_forensic_report_stable(mock_file, validator):
    # curr_vol should be near 0.0012 for drift < 0.25
    df = generate_vol_df(0.0012, length=1000)
    score = validator.generate_forensic_report("EURUSD", df)

    assert score < 0.25
    mock_file.assert_called_with(validator.report_path, "w", encoding='utf-8')

    # Check if "✅ STABLE" is in the written content
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "✅ STABLE" in written_content
    assert "EURUSD" in written_content

@patch("builtins.open", new_callable=mock_open)
def test_generate_forensic_report_drifting(mock_file, validator):
    # drift = abs(curr_vol - 0.0012) / 0.0012
    # For drift ~ 0.3, curr_vol ~ 0.00156
    df = generate_vol_df(0.00156, length=1000)
    score = validator.generate_forensic_report("EURUSD", df)

    assert 0.25 <= score <= 0.5
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "⚠️ DRIFTING" in written_content

@patch("builtins.open", new_callable=mock_open)
def test_generate_forensic_report_critical(mock_file, validator):
    # For drift ~ 0.6, curr_vol ~ 0.00192
    df = generate_vol_df(0.00192, length=1000)
    score = validator.generate_forensic_report("EURUSD", df)

    assert score > 0.5
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "🚨 CRITICAL" in written_content

@patch("builtins.open", new_callable=mock_open)
def test_data_integrity_check(mock_file, validator):
    # Test Pass
    df_pass = pd.DataFrame({"close": [1.0, 1.1, 1.2]})
    validator.generate_forensic_report("EURUSD", df_pass)
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "[x] Data Integrity: Pass" in written_content

    # Test Fail (NaNs)
    mock_file.reset_mock()
    df_fail = pd.DataFrame({"close": [1.0, np.nan, 1.2]})
    validator.generate_forensic_report("EURUSD", df_fail)
    handle = mock_file()
    written_content = "".join(call.args[0] for call in handle.write.call_args_list)
    assert "[ ] Data Integrity: Pass" in written_content
