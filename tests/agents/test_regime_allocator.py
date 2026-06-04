import sys
from unittest.mock import MagicMock

# Define a tool decorator that returns the original function
def mock_tool_decorator(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

# Mock FastMCP before importing the module that uses it
mock_mcp = MagicMock()
mock_mcp.tool = MagicMock(side_effect=mock_tool_decorator)

sys.modules["mcp"] = MagicMock()
sys.modules["mcp.server"] = MagicMock()
sys.modules["mcp.server.fastmcp"] = MagicMock()
sys.modules["mcp.server.fastmcp"].FastMCP = MagicMock(return_value=mock_mcp)

import pytest
import json
from agents.regime_allocator import evaluate_regime_allocation, get_market_regime

def test_evaluate_regime_allocation_volatile_anomaly():
    fft_data = {"anomaly_detected": True, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("BTCUSD", "BULL", fft_data)
    assert result["regime"] == "VOLATILE"
    assert result["authorized_strategy"] == "STEP_ASIDE"
    assert result["momentum_locked"] is True

def test_evaluate_regime_allocation_volatile_sigma():
    fft_data = {"anomaly_detected": False, "volatility_sigma": 5.0}
    result = evaluate_regime_allocation("BTCUSD", "BULL", fft_data)
    assert result["regime"] == "VOLATILE"
    assert result["authorized_strategy"] == "STEP_ASIDE"
    assert result["momentum_locked"] is True

def test_evaluate_regime_allocation_range():
    fft_data = {"anomaly_detected": False, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("BTCUSD", "RANGE", fft_data)
    assert result["regime"] == "RANGE"
    assert result["authorized_strategy"] == "WILLIAMS_WYCKOFF"
    assert result["momentum_locked"] is True

def test_evaluate_regime_allocation_trend_bull():
    fft_data = {"anomaly_detected": False, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("BTCUSD", "BULL", fft_data)
    assert result["regime"] == "TREND"
    assert result["authorized_strategy"] == "KRONOS_MOMENTUM"
    assert result["momentum_locked"] is False

def test_evaluate_regime_allocation_trend_bear():
    fft_data = {"anomaly_detected": False, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("BTCUSD", "BEAR", fft_data)
    assert result["regime"] == "TREND"
    assert result["authorized_strategy"] == "KRONOS_MOMENTUM"
    assert result["momentum_locked"] is False

def test_evaluate_regime_allocation_uncertain():
    fft_data = {"anomaly_detected": False, "volatility_sigma": 2.0}
    result = evaluate_regime_allocation("BTCUSD", "UNKNOWN", fft_data)
    assert result["regime"] == "UNCERTAIN"
    assert result["authorized_strategy"] == "STEP_ASIDE"
    assert result["momentum_locked"] is True

def test_get_market_regime_success():
    fft_data_json = json.dumps({"anomaly_detected": False, "volatility_sigma": 2.0})
    result_json = get_market_regime("BTCUSD", "BULL", fft_data_json)
    result = json.loads(result_json)
    assert result["regime"] == "TREND"
    assert result["symbol"] == "BTCUSD"

def test_get_market_regime_invalid_json():
    result_json = get_market_regime("BTCUSD", "BULL", "invalid json")
    result = json.loads(result_json)
    assert "error" in result
