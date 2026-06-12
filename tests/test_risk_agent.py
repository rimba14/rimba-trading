import sys
from unittest.mock import MagicMock
import pytest

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import parse_base_quote, calculate_currency_exposure, get_usd_rate

def test_get_usd_rate_direct(mocker):
    """Test get_usd_rate for direct rates (e.g. GBPUSD)."""
    mock_mt5 = sys.modules['MetaTrader5']
    mock_tick = MagicMock()
    mock_tick.bid = 1.25
    mock_mt5.symbol_info_tick.return_value = mock_tick

    # Reset mock to clear previous calls
    mock_mt5.symbol_info_tick.reset_mock(return_value=True, side_effect=True)
    mock_mt5.symbol_info_tick.return_value = mock_tick

    rate = get_usd_rate("GBP")
    assert rate == 1.25
    mock_mt5.symbol_info_tick.assert_called_with("GBPUSD")

def test_get_usd_rate_inverse(mocker):
    """Test get_usd_rate for inverse rates (e.g. USDJPY)."""
    mock_mt5 = sys.modules['MetaTrader5']
    mock_mt5.symbol_info_tick.reset_mock(return_value=True, side_effect=True)

    mock_tick = MagicMock()
    mock_tick.bid = 110.0
    # First call (direct GBPUSD) returns None, second (inverse USDJPY) returns tick
    mock_mt5.symbol_info_tick.side_effect = [None, mock_tick]

    rate = get_usd_rate("JPY")
    assert rate == 1.0 / 110.0
    assert mock_mt5.symbol_info_tick.call_count == 2

def test_get_usd_rate_exception(mocker):
    """Test get_usd_rate returns 1.0 and logs error on exception."""
    mock_mt5 = sys.modules['MetaTrader5']
    mock_mt5.symbol_info_tick.reset_mock(return_value=True, side_effect=True)
    mock_mt5.symbol_info_tick.side_effect = Exception("MT5 Connection Failed")

    mock_logger = mocker.patch("agents.risk_agent.logger")

    rate = get_usd_rate("EUR")
    assert rate == 1.0
    mock_logger.error.assert_called_once()
    assert "Error fetching USD rate for EUR" in mock_logger.error.call_args[0][0]

def test_calculate_currency_exposure_with_usd_rate_failure(mocker):
    """Test calculate_currency_exposure when get_usd_rate fails (returns fallback 1.0)."""
    mock_mt5 = sys.modules['MetaTrader5']
    mock_mt5.symbol_info_tick.reset_mock(return_value=True, side_effect=True)
    # Force get_usd_rate to fail by raising exception in symbol_info_tick
    mock_mt5.symbol_info_tick.side_effect = Exception("MT5 Error")

    # Mock symbol_info to return a valid object for contract size
    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    mock_logger = mocker.patch("agents.risk_agent.logger")

    class MockPosition:
        def __init__(self, symbol, volume, price_open, sl, type):
            self.symbol = symbol
            self.volume = volume
            self.price_open = price_open
            self.sl = sl
            self.type = type

    # Use a non-USD quote to trigger get_usd_rate failure
    positions = [MockPosition("EURGBP", 0.1, 0.85, 0.84, 0)] # BUY EURGBP
    # sl_dist = 0.01, risk_quote = 0.01 * 0.1 * 100000 = 100 GBP
    # get_usd_rate("GBP") will fail and return 1.0
    # risk_usd = 100 * 1.0 = 100 USD

    exposures = calculate_currency_exposure(positions)

    assert pytest.approx(exposures["EUR"]) == 100.0
    assert pytest.approx(exposures["GBP"]) == -100.0
    # Verify logger.error was called by get_usd_rate
    mock_logger.error.assert_called()

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
