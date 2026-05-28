import sys
from unittest.mock import MagicMock
import pytest

# Mock MetaTrader5 module before importing from risk_agent
sys.modules['MetaTrader5'] = MagicMock()

import os
import datetime
from unittest.mock import patch

# Add the project root to sys.path so agents module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.risk_agent import parse_base_quote, check_upcoming_tier1_events

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


@patch('agents.risk_agent.datetime')
def test_check_upcoming_tier1_events_imminent(mock_datetime):
    # Jan 3 2024 is a Wednesday (weekday=2)
    mock_now = datetime.datetime(2024, 1, 3, 12, 0)
    mock_datetime.datetime.utcnow.return_value = mock_now
    mock_datetime.timedelta = datetime.timedelta

    # FOMC is Wednesday 14:00 (2 hours from mock_now)
    # Using USDJPY to avoid EUR events that might trigger first
    is_imminent, event_name = check_upcoming_tier1_events("USDJPY", threshold_hours=24.0)
    assert is_imminent is True
    assert event_name == "FOMC Rate Decision in 2.0h"

@patch('agents.risk_agent.datetime')
def test_check_upcoming_tier1_events_out_of_threshold(mock_datetime):
    # Jan 3 2024, 12:00 (Wed)
    mock_now = datetime.datetime(2024, 1, 3, 12, 0)
    mock_datetime.datetime.utcnow.return_value = mock_now
    mock_datetime.timedelta = datetime.timedelta

    # FOMC is 2 hours away, but we set threshold to 1 hour
    is_imminent, event_name = check_upcoming_tier1_events("EURUSD", threshold_hours=1.0)
    assert is_imminent is False
    assert event_name == ""

@patch('agents.risk_agent.datetime')
def test_check_upcoming_tier1_events_base_quote(mock_datetime):
    # Jan 4 2024, 8:00 (Thursday, weekday=3)
    mock_now = datetime.datetime(2024, 1, 4, 8, 0)
    mock_datetime.datetime.utcnow.return_value = mock_now
    mock_datetime.timedelta = datetime.timedelta

    # ECB Rate Decision is Thursday 8:15 (0.25 hours away)
    # Testing EUR base
    is_imminent, event_name = check_upcoming_tier1_events("EURGBP", threshold_hours=24.0)
    assert is_imminent is True
    assert event_name == "ECB Rate Decision in 0.2h"

@patch('agents.risk_agent.datetime')
def test_check_upcoming_tier1_events_non_6_char_usd(mock_datetime):
    # Jan 5 2024, 6:00 (Friday, weekday=4)
    mock_now = datetime.datetime(2024, 1, 5, 6, 0)
    mock_datetime.datetime.utcnow.return_value = mock_now
    mock_datetime.timedelta = datetime.timedelta

    # NFP is Friday 8:30 (2.5 hours away)
    # Testing non-6 char symbol with "USD"
    is_imminent, event_name = check_upcoming_tier1_events("BTCUSD.M", threshold_hours=24.0)
    assert is_imminent is True
    assert event_name == "Non-Farm Payrolls (NFP) in 2.5h"

@patch('agents.risk_agent.datetime')
def test_check_upcoming_tier1_events_wrap_around(mock_datetime):
    # Jan 5 2024, 12:00 (Friday, weekday=4)
    mock_now = datetime.datetime(2024, 1, 5, 12, 0)
    mock_datetime.datetime.utcnow.return_value = mock_now
    mock_datetime.timedelta = datetime.timedelta

    # Event has passed (NFP was 8:30 today). Next NFP is next week (164.5 hours away)
    # Wrap around handles it properly and sees it's not imminent
    is_imminent, event_name = check_upcoming_tier1_events("USDJPY", threshold_hours=24.0)

    # Wait, there's no upcoming event within 24h.
    assert is_imminent is False
    assert event_name == ""
