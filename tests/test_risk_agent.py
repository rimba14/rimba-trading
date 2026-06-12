import sys
from unittest.mock import MagicMock
import pytest

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import parse_base_quote, calculate_currency_exposure, get_usd_rate

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

def test_calculate_currency_exposure_error_path(mocker):
    """Test that calculate_currency_exposure handles parsing exceptions gracefully."""
    class MockPositionWithException:
        @property
        def symbol(self):
            raise ValueError("Simulated parsing error")

    mock_logger = mocker.patch("agents.risk_agent.logger")

    positions = [MockPositionWithException()]
    exposures = calculate_currency_exposure(positions)

    assert exposures == {}
    mock_logger.warning.assert_called_once()
    call_arg = mock_logger.warning.call_args[0][0]
    assert "[RISK_EXPOSURE_ERR] Failed parsing position" in call_arg

def test_get_usd_rate(mocker):
    """Test get_usd_rate for various currency scenarios including USD, direct, inverse, and fallback."""
    import MetaTrader5 as mt5

    # 1. Test USD case
    assert get_usd_rate("USD") == 1.0

    # 2. Test Direct Rate (e.g. GBPUSD)
    mock_tick_gbp = MagicMock()
    mock_tick_gbp.bid = 1.25

    def side_effect(symbol):
        if symbol == "GBPUSD":
            return mock_tick_gbp
        return None

    mocker.patch("MetaTrader5.symbol_info_tick", side_effect=side_effect)
    assert get_usd_rate("GBP") == 1.25

    # 3. Test Inverse Rate (e.g. USDJPY)
    mock_tick_jpy = MagicMock()
    mock_tick_jpy.bid = 110.0

    def side_effect_inverse(symbol):
        if symbol == "USDJPY":
            return mock_tick_jpy
        return None

    mocker.patch("MetaTrader5.symbol_info_tick", side_effect=side_effect_inverse)
    # 1.0 / 110.0 is approx 0.009090909
    assert get_usd_rate("JPY") == pytest.approx(1.0 / 110.0)

    # 4. Test Fallback Case
    mocker.patch("MetaTrader5.symbol_info_tick", return_value=None)
    assert get_usd_rate("XYZ") == 1.0
