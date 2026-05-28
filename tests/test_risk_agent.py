import sys
from unittest.mock import MagicMock
import pytest

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import parse_base_quote, get_usd_rate
import agents.risk_agent

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

def test_get_usd_rate_usd_base():
    """Test base case when currency is already USD."""
    assert get_usd_rate("USD") == 1.0

def test_get_usd_rate_direct_pair(mocker):
    """Test conversion rate for a direct pair like GBPUSD."""
    mock_tick = MagicMock()
    mock_tick.bid = 1.25

    def mock_symbol_info_tick(symbol):
        if symbol == "GBPUSD":
            return mock_tick
        return None

    mocker.patch('agents.risk_agent.mt5.symbol_info_tick', side_effect=mock_symbol_info_tick)
    assert get_usd_rate("GBP") == 1.25

def test_get_usd_rate_inverse_pair(mocker):
    """Test conversion rate for an inverse pair like USDJPY."""
    mock_tick = MagicMock()
    mock_tick.bid = 150.0

    def mock_symbol_info_tick(symbol):
        if symbol == "USDJPY":
            return mock_tick
        return None

    mocker.patch('agents.risk_agent.mt5.symbol_info_tick', side_effect=mock_symbol_info_tick)
    assert get_usd_rate("JPY") == 1.0 / 150.0

def test_get_usd_rate_fallback(mocker):
    """Test fallback when neither direct nor inverse rate is available."""
    mocker.patch('agents.risk_agent.mt5.symbol_info_tick', return_value=None)
    assert get_usd_rate("XYZ") == 1.0

def test_get_usd_rate_zero_bid_fallback(mocker):
    """Test fallback when tick bid is zero or invalid."""
    mock_tick = MagicMock()
    mock_tick.bid = 0.0

    mocker.patch('agents.risk_agent.mt5.symbol_info_tick', return_value=mock_tick)
    assert get_usd_rate("XYZ") == 1.0
