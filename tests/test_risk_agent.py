import sys
from unittest.mock import MagicMock
import pytest
import datetime

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import parse_base_quote, calculate_currency_exposure, check_upcoming_tier1_events

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

def test_check_upcoming_tier1_events_imminent(mocker):
    """Test imminent macro event for USDCAD (FOMC)."""
    # Wed Oct 25 13:00:00 2023 is a Wednesday (weekday 2)
    # FOMC is Wednesday 14:00
    mock_now = datetime.datetime(2023, 10, 25, 13, 0)
    class MockDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return mock_now
    mocker.patch("agents.risk_agent.datetime.datetime", MockDateTime)

    # Use USDCAD to avoid EUR/GBP events interference in this specific test
    is_imminent, desc = check_upcoming_tier1_events("USDCAD")
    assert is_imminent is True
    assert "FOMC Rate Decision" in desc

def test_check_upcoming_tier1_events_not_imminent(mocker):
    """Test macro event for EURUSD more than 24h away."""
    # Tue Oct 24 13:00:00 2023 is a Tuesday (weekday 1)
    # FOMC is Wed 14:00 (25h away), ECB is Thu 08:15 (>36h away), BOE is Thu 07:00
    mock_now = datetime.datetime(2023, 10, 24, 13, 0)
    class MockDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return mock_now
    mocker.patch("agents.risk_agent.datetime.datetime", MockDateTime)

    is_imminent, desc = check_upcoming_tier1_events("EURUSD")
    assert is_imminent is False
    assert desc == ""

def test_check_upcoming_tier1_events_msft_earnings(mocker):
    """Test imminent MSFT earnings."""
    # MSFT Earnings: Tue 16:00 (weekday 1)
    # Mocking Tue 15:00 UTC
    mock_now = datetime.datetime(2023, 10, 24, 15, 0)
    class MockDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return mock_now
    mocker.patch("agents.risk_agent.datetime.datetime", MockDateTime)

    is_imminent, desc = check_upcoming_tier1_events("MSFT")
    assert is_imminent is True
    assert "MSFT Q3 Earnings" in desc

def test_check_upcoming_tier1_events_btcusd_fallback(mocker):
    """Test BTCUSD picking up USD macro events."""
    # FOMC: Wed 14:00 (weekday 2)
    # Mocking Wed 13:00 UTC
    mock_now = datetime.datetime(2023, 10, 25, 13, 0)
    class MockDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return mock_now
    mocker.patch("agents.risk_agent.datetime.datetime", MockDateTime)

    is_imminent, desc = check_upcoming_tier1_events("BTCUSD")
    assert is_imminent is True
    assert "FOMC Rate Decision" in desc

def test_check_upcoming_tier1_events_no_event(mocker):
    """Test symbol with no calendar events."""
    mock_now = datetime.datetime(2023, 10, 25, 13, 0)
    class MockDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return mock_now
    mocker.patch("agents.risk_agent.datetime.datetime", MockDateTime)

    is_imminent, desc = check_upcoming_tier1_events("XYZABC")
    assert is_imminent is False
    assert desc == ""
