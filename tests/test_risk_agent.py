import sys
import os
from unittest.mock import MagicMock
import pytest

# Add current dir to sys.path so agents module can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import parse_base_quote, calculate_volatility_scalar

def test_parse_base_quote_standard_forex():
    """Test standard 6-character clean forex pairs."""
    assert parse_base_quote("EURUSD") == ("EUR", "USD")
    assert parse_base_quote("GBPUSD") == ("GBP", "USD")
    assert parse_base_quote("USDJPY") == ("USD", "JPY")

def test_parse_base_quote_with_suffixes():
    """Test standard pairs with suffixes like .M, .R, .T, and '-' separated."""
    assert parse_base_quote("EURUSD.M") == ("EUR", "USD")
    assert parse_base_quote("GBPUSD.R") == ("GBP", "USD")
    assert parse_base_quote("USDJPY.T") == ("USD", "JPY")
    assert parse_base_quote("AUDUSD-pro") == ("AUD", "USD")

def test_parse_base_quote_metals():
    """Test specific metal custom overrides."""
    assert parse_base_quote("XAUUSD") == ("XAU", "USD")
    assert parse_base_quote("GOLD") == ("XAU", "USD")
    assert parse_base_quote("XAGUSD") == ("XAG", "USD")
    assert parse_base_quote("SILVER") == ("XAG", "USD")
    assert parse_base_quote("GOLD.M") == ("XAU", "USD")

def test_parse_base_quote_indices_and_fallbacks():
    """Test specific index overrides and general fallbacks."""
    assert parse_base_quote("GER40") == ("EUR", "USD")
    assert parse_base_quote("FRA40") == ("EUR", "USD")
    assert parse_base_quote("US30") == ("US30", "USD")
    assert parse_base_quote("SPX500") == ("SPX500", "USD")

def test_calculate_volatility_scalar_normal():
    """Test standard calculation without clamping."""
    # EURUSD baseline is 0.0050. current_atr = 0.01 -> scalar = 0.5
    # Use pytest.approx or math.isclose due to 1e-12 addition
    import math
    assert math.isclose(calculate_volatility_scalar("EURUSD", 0.01), 0.5, rel_tol=1e-9)
    # BTC baseline is 1200.0. current_atr = 2400.0 -> scalar = 0.5
    assert math.isclose(calculate_volatility_scalar("BTCUSD", 2400.0), 0.5, rel_tol=1e-9)

def test_calculate_volatility_scalar_clamped():
    """Test that scalar does not exceed 1.0 in low volatility environments."""
    # EURUSD baseline is 0.0050. current_atr = 0.001 -> scalar = 5.0 (clamped to 1.0)
    assert calculate_volatility_scalar("EURUSD", 0.001) == 1.0
    # US30 baseline is 150.0. current_atr = 100.0 -> scalar = 1.5 (clamped to 1.0)
    assert calculate_volatility_scalar("US30", 100.0) == 1.0

def test_calculate_volatility_scalar_zero_atr():
    """Test protection against division by zero."""
    # Division by zero should not raise an error, and should clamp to 1.0
    assert calculate_volatility_scalar("EURUSD", 0.0) == 1.0
    assert calculate_volatility_scalar("GOLD", 0.0) == 1.0
