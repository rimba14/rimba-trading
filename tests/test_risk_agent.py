import sys
from unittest.mock import MagicMock
import pytest
from typing import Dict

# Mock MetaTrader5 module before importing from risk_agent
mock_mt5 = MagicMock()
sys.modules['MetaTrader5'] = mock_mt5

from agents.risk_agent import parse_base_quote, calculate_currency_exposure

class MockPosition:
    def __init__(self, symbol, sl, price_open, volume, p_type):
        self.symbol = symbol
        self.sl = sl
        self.price_open = price_open
        self.volume = volume
        self.type = p_type

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

def test_calculate_currency_exposure_error_path(monkeypatch):
    """Test that calculate_currency_exposure handles parsing exceptions gracefully."""
    class MockPositionWithException:
        @property
        def symbol(self):
            raise ValueError("Simulated parsing error")

    mock_logger = MagicMock()
    monkeypatch.setattr("agents.risk_agent.logger", mock_logger)

    positions = [MockPositionWithException()]
    exposures = calculate_currency_exposure(positions)

    assert exposures == {}
    mock_logger.warning.assert_called_once()
    call_arg = mock_logger.warning.call_args[0][0]
    assert "[RISK_EXPOSURE_ERR] Failed parsing position" in call_arg

def test_calculate_currency_exposure_empty():
    """Verifies that an empty list of positions returns an empty dictionary."""
    assert calculate_currency_exposure([]) == {}
    assert calculate_currency_exposure(None) == {}

def test_calculate_currency_exposure_forex_buy_with_sl():
    """Verifies risk calculation and directional aggregation for a standard BUY position (EURUSD) with a Stop Loss."""
    # Setup
    positions = [MockPosition("EURUSD", 1.0900, 1.1000, 0.1, 0)] # BUY 0.1 lots EURUSD, entry 1.10, SL 1.09

    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    # EURUSD doesn't need rate conversion as quote is USD

    # Execution
    exposures = calculate_currency_exposure(positions)

    # Verification
    # sl_dist = abs(1.1000 - 1.0900) = 0.01
    # risk_quote = 0.01 * 0.1 * 100000.0 = 100.0 USD
    # BUY: Long EUR (+100), Short USD (-100)
    assert exposures["EUR"] == pytest.approx(100.0)
    assert exposures["USD"] == pytest.approx(-100.0)

def test_calculate_currency_exposure_forex_sell_no_sl():
    """Verifies the 2% notional fallback risk calculation for a SELL position without a Stop Loss."""
    # Setup
    positions = [MockPosition("GBPUSD", 0.0, 1.3000, 0.1, 1)] # SELL 0.1 lots GBPUSD, entry 1.30, NO SL

    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    # Execution
    exposures = calculate_currency_exposure(positions)

    # Verification
    # risk_quote = 0.1 * 1.3000 * 100000.0 * 0.02 = 260.0 USD
    # SELL: Short GBP (-260), Long USD (+260)
    assert exposures["GBP"] == pytest.approx(-260.0)
    assert exposures["USD"] == pytest.approx(260.0)

def test_calculate_currency_exposure_cross_rate():
    """Verifies that quote currencies other than USD (e.g., GBP in EURGBP) are correctly converted to USD."""
    # Setup
    positions = [MockPosition("EURGBP", 0.8400, 0.8500, 0.1, 0)] # BUY 0.1 lots EURGBP, entry 0.85, SL 0.84

    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    # Mock get_usd_rate for GBP
    mock_tick = MagicMock()
    mock_tick.bid = 1.3000
    mock_mt5.symbol_info_tick.side_effect = lambda sym: mock_tick if sym == "GBPUSD" else None

    # Execution
    exposures = calculate_currency_exposure(positions)

    # Verification
    # sl_dist = 0.85 - 0.84 = 0.01
    # risk_quote = 0.01 * 0.1 * 100000.0 = 100.0 GBP
    # risk_usd = 100.0 * 1.3000 = 130.0 USD
    # BUY: Long EUR (+130), Short GBP (-130)
    assert exposures["EUR"] == pytest.approx(130.0)
    assert exposures["GBP"] == pytest.approx(-130.0)

def test_calculate_currency_exposure_inverse_rate():
    """Verifies USD conversion using an inverse rate (e.g., JPY in USDJPY)."""
    # Setup
    positions = [MockPosition("AUDJPY", 94.0, 95.0, 0.1, 1)] # SELL 0.1 lots AUDJPY, entry 95.0, SL 94.0

    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    # Mock get_usd_rate for JPY
    # get_usd_rate("JPY") will try JPYUSD (fail) then USDJPY (success)
    mock_tick = MagicMock()
    mock_tick.bid = 150.0
    mock_mt5.symbol_info_tick.side_effect = lambda sym: mock_tick if sym == "USDJPY" else None

    # Execution
    exposures = calculate_currency_exposure(positions)

    # Verification
    # sl_dist = abs(95.0 - 94.0) = 1.0
    # risk_quote = 1.0 * 0.1 * 100000.0 = 10000.0 JPY
    # rate = 1.0 / 150.0 = 0.006666...
    # risk_usd = 10000.0 / 150.0 = 66.666...
    # SELL AUDJPY: Short AUD (-66.66), Long JPY (+66.66)
    assert exposures["AUD"] == pytest.approx(-66.66666666666667)
    assert exposures["JPY"] == pytest.approx(66.66666666666667)

def test_calculate_currency_exposure_aggregation():
    """Verifies that exposures from multiple positions are correctly aggregated."""
    # Setup
    positions = [
        MockPosition("EURUSD", 1.0900, 1.1000, 0.1, 0), # BUY EURUSD: EUR +100, USD -100
        MockPosition("GBPUSD", 1.2900, 1.3000, 0.1, 0), # BUY GBPUSD: GBP +100, USD -100
        MockPosition("EURGBP", 0.8400, 0.8500, 0.1, 1)  # SELL EURGBP: EUR -130, GBP +130 (assuming GBPUSD=1.3)
    ]

    mock_sym_info = MagicMock()
    mock_sym_info.trade_contract_size = 100000.0
    mock_mt5.symbol_info.return_value = mock_sym_info

    mock_tick = MagicMock()
    mock_tick.bid = 1.3000
    mock_mt5.symbol_info_tick.side_effect = lambda sym: mock_tick if sym == "GBPUSD" else None

    # Execution
    exposures = calculate_currency_exposure(positions)

    # Verification
    # EUR: +100 (from EURUSD) - 130 (from EURGBP) = -30
    # GBP: +100 (from GBPUSD) + 130 (from EURGBP) = +230
    # USD: -100 (from EURUSD) - 100 (from GBPUSD) = -200
    assert exposures["EUR"] == pytest.approx(-30.0)
    assert exposures["GBP"] == pytest.approx(230.0)
    assert exposures["USD"] == pytest.approx(-200.0)
