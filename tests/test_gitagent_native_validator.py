import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, mock_open
from gitagent_native_validator import NativeSentinelValidator

def test_calculate_drift_baseline_zero():
    validator = NativeSentinelValidator()
    assert validator.calculate_drift(0.0, 0.0012) == 0.0

def test_calculate_drift_no_drift():
    validator = NativeSentinelValidator()
    assert validator.calculate_drift(0.0012, 0.0012) == 0.0

def test_calculate_drift_positive_drift():
    validator = NativeSentinelValidator()
    # abs(0.0015 - 0.0012) / 0.0012 = 0.0003 / 0.0012 = 0.25
    assert validator.calculate_drift(0.0012, 0.0015) == pytest.approx(0.25)

def test_calculate_drift_negative_drift():
    validator = NativeSentinelValidator()
    # abs(0.0009 - 0.0012) / 0.0012 = 0.0003 / 0.0012 = 0.25
    assert validator.calculate_drift(0.0012, 0.0009) == pytest.approx(0.25)

def test_generate_forensic_report():
    validator = NativeSentinelValidator()

    # Simple data to ensure pct_change() doesn't produce all NaNs
    data = {"close": [100.0, 100.12, 100.24, 100.12, 100.0]}
    df = pd.DataFrame(data)

    # We mock open to avoid writing to C:\Sentinel_Project\SENTINEL_DASHBOARD.md
    with patch("builtins.open", mock_open()) as mocked_file:
        drift_score = validator.generate_forensic_report("TEST_SYMBOL", df)

        # Verify drift_score is a float
        assert isinstance(drift_score, float)

        # Verify it was called with the report path
        mocked_file.assert_called_once_with(validator.report_path, "w", encoding='utf-8')
