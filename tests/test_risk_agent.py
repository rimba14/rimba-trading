import sys
from unittest.mock import MagicMock, patch
import pytest

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import parse_base_quote, calculate_currency_exposure

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

def test_parse_base_quote_crypto_and_extra():
    """Test crypto symbols and case sensitivity."""
    # 6-char crypto (no digits) should work like forex
    assert parse_base_quote("BTCUSD") == ("BTC", "USD")
    assert parse_base_quote("btcusd") == ("BTC", "USD")

    # 7-char or longer crypto should fall back
    assert parse_base_quote("DOGEUSD") == ("DOGEUSD", "USD")
    assert parse_base_quote("SHIBUSD") == ("SHIBUSD", "USD")

def test_parse_base_quote_edge_cases():
    """Test unusual symbols and edge cases."""
    assert parse_base_quote("") == ("", "USD")
    assert parse_base_quote("A") == ("A", "USD")
    assert parse_base_quote("ABCDEF") == ("ABC", "DEF")
    assert parse_base_quote("ABC-DEF") == ("ABC", "USD")
    assert parse_base_quote("EURUSD.X") == ("EURUSD.X", "USD") # .X is not cleaned

def test_calculate_currency_exposure_error_path():
    """Test that calculate_currency_exposure handles parsing exceptions gracefully."""
    class MockPositionWithException:
        @property
        def symbol(self):
            raise ValueError("Simulated parsing error")

    with patch("agents.risk_agent.logger") as mock_logger:
        positions = [MockPositionWithException()]
        exposures = calculate_currency_exposure(positions)

        assert exposures == {}
        mock_logger.warning.assert_called_once()
        call_arg = mock_logger.warning.call_args[0][0]
        assert "[RISK_EXPOSURE_ERR] Failed parsing position" in call_arg
