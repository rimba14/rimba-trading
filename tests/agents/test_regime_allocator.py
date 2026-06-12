import pytest
import sys
import json
from unittest.mock import MagicMock

# Mock out mcp.server.fastmcp before importing the module under test
class MockFastMCP:
    def __init__(self, *args, **kwargs):
        pass
    def tool(self):
        def decorator(func):
            return func
        return decorator
    def run(self):
        pass

mock_mcp_module = MagicMock()
mock_mcp_module.FastMCP = MockFastMCP
sys.modules['mcp.server.fastmcp'] = mock_mcp_module

import os
import importlib.util
from unittest.mock import MagicMock

# Dynamically load the module to bypass absolute import path issues in pytest
module_name = "agents.regime_allocator"
file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../agents/regime_allocator.py'))

spec = importlib.util.spec_from_file_location(module_name, file_path)
regime_allocator = importlib.util.module_from_spec(spec)
sys.modules[module_name] = regime_allocator
spec.loader.exec_module(regime_allocator)

evaluate_regime_allocation = regime_allocator.evaluate_regime_allocation
get_market_regime = regime_allocator.get_market_regime

def test_evaluate_regime_allocation_volatile_anomaly():
    # Test State 3: VOLATILE due to anomaly_detected
    fft_data = {"anomaly_detected": True, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("BTCUSD", "RANGE", fft_data)
    assert result == {
        "symbol": "BTCUSD",
        "regime": "VOLATILE",
        "authorized_strategy": "STEP_ASIDE",
        "momentum_locked": True
    }

def test_evaluate_regime_allocation_volatile_sigma():
    # Test State 3: VOLATILE due to volatility_sigma > 4.0
    fft_data = {"anomaly_detected": False, "volatility_sigma": 4.5}
    result = evaluate_regime_allocation("BTCUSD", "BULL", fft_data)
    assert result == {
        "symbol": "BTCUSD",
        "regime": "VOLATILE",
        "authorized_strategy": "STEP_ASIDE",
        "momentum_locked": True
    }

def test_evaluate_regime_allocation_range():
    # Test State 1: RANGE
    fft_data = {"anomaly_detected": False, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("EURUSD", "RANGE", fft_data)
    assert result == {
        "symbol": "EURUSD",
        "regime": "RANGE",
        "authorized_strategy": "WILLIAMS_WYCKOFF",
        "momentum_locked": True
    }

def test_evaluate_regime_allocation_trend_bull():
    # Test State 2: TREND (Bull)
    fft_data = {"anomaly_detected": False, "volatility_sigma": 1.5}
    result = evaluate_regime_allocation("SPX500", "BULL", fft_data)
    assert result == {
        "symbol": "SPX500",
        "regime": "TREND",
        "authorized_strategy": "KRONOS_MOMENTUM",
        "momentum_locked": False
    }

def test_evaluate_regime_allocation_trend_bear():
    # Test State 2: TREND (Bear)
    fft_data = {"anomaly_detected": False, "volatility_sigma": 3.0}
    result = evaluate_regime_allocation("NAS100", "BEAR", fft_data)
    assert result == {
        "symbol": "NAS100",
        "regime": "TREND",
        "authorized_strategy": "KRONOS_MOMENTUM",
        "momentum_locked": False
    }

def test_evaluate_regime_allocation_uncertain():
    # Test Default Fallback
    fft_data = {"anomaly_detected": False, "volatility_sigma": 1.0}
    result = evaluate_regime_allocation("GOLD", "UNKNOWN_STATE", fft_data)
    assert result == {
        "symbol": "GOLD",
        "regime": "UNCERTAIN",
        "authorized_strategy": "STEP_ASIDE",
        "momentum_locked": True
    }

def test_get_market_regime_valid_json():
    # Test valid JSON input
    fft_data = {"anomaly_detected": False, "volatility_sigma": 2.0}
    fft_json = json.dumps(fft_data)

    result_json = get_market_regime("EURUSD", "RANGE", fft_json)

    expected_dict = {
        "symbol": "EURUSD",
        "regime": "RANGE",
        "authorized_strategy": "WILLIAMS_WYCKOFF",
        "momentum_locked": True
    }

    assert json.loads(result_json) == expected_dict
    assert result_json == json.dumps(expected_dict, indent=2)

def test_get_market_regime_invalid_json():
    # Test invalid JSON input
    invalid_json = "{invalid_json}"
    result_json = get_market_regime("EURUSD", "RANGE", invalid_json)

    parsed_result = json.loads(result_json)
    assert "error" in parsed_result

def test_evaluate_regime_allocation_volatility_boundary():
    # Test volatility_sigma exactly at 4.0 (should NOT be VOLATILE)
    fft_data = {"anomaly_detected": False, "volatility_sigma": 4.0}
    result = evaluate_regime_allocation("BTCUSD", "RANGE", fft_data)
    assert result["regime"] == "RANGE"

def test_evaluate_regime_allocation_empty_fft_data():
    # Test empty dictionary for fft_amplitude_data
    result = evaluate_regime_allocation("BTCUSD", "BULL", {})
    assert result["regime"] == "TREND"
    assert result["authorized_strategy"] == "KRONOS_MOMENTUM"

def test_get_market_regime_non_dict_json():
    # Test JSON that is valid but not a dictionary (e.g., a number)
    # json.loads("123") returns 123, then evaluate_regime_allocation(..., 123)
    # which will likely raise an AttributeError when calling .get()
    result_json = get_market_regime("BTCUSD", "BULL", "123")
    parsed_result = json.loads(result_json)
    assert "error" in parsed_result

def test_evaluate_regime_allocation_empty_hmm_state():
    # Test empty string for hmm_state
    fft_data = {"anomaly_detected": False, "volatility_sigma": 1.0}
    result = evaluate_regime_allocation("BTCUSD", "", fft_data)
    assert result["regime"] == "UNCERTAIN"
    assert result["authorized_strategy"] == "STEP_ASIDE"
