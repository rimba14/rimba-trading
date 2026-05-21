import sys
import datetime
from unittest.mock import MagicMock, patch

# Mock MetaTrader5 to avoid ModuleNotFoundError in CI
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import check_upcoming_tier1_events, STATIC_MACRO_CALENDAR

def test_check_upcoming_tier1_events_no_event():
    # Set a time far away from events
    mock_now = datetime.datetime(2023, 10, 10, 12, 0, 0) # Tuesday
    with patch('agents.risk_agent.datetime') as mock_datetime:
        mock_datetime.datetime.utcnow.return_value = mock_now
        mock_datetime.timedelta = datetime.timedelta # Keep real timedelta behavior

        has_event, msg = check_upcoming_tier1_events("AUDCAD", threshold_hours=24.0)
        assert not has_event
        assert msg == ""

def test_check_upcoming_tier1_events_imminent_event_base():
    # "EUR": [(3, 8, 15, "ECB Rate Decision")] -> Thursday 8:15 AM
    # Let's set the time to Thursday 7:00 AM (1.25 hours away)
    mock_now = datetime.datetime(2023, 10, 12, 7, 0, 0) # Thursday 7:00 AM

    with patch('agents.risk_agent.datetime') as mock_datetime:
        mock_datetime.datetime.utcnow.return_value = mock_now
        mock_datetime.timedelta = datetime.timedelta

        # Test just the base symbol logic
        has_event, msg = check_upcoming_tier1_events("EURGBP", threshold_hours=24.0)
        assert has_event
        assert "ECB Rate Decision" in msg
        assert "in 1.2h" in msg

def test_check_upcoming_tier1_events_imminent_event_quote():
    # "GBP": [(3, 7, 0, "BOE Rate Decision")] -> Thursday 7:00 AM
    # Let's set time to Wednesday 12:00 PM (19 hours away)
    mock_now = datetime.datetime(2023, 10, 11, 12, 0, 0) # Wednesday

    with patch('agents.risk_agent.datetime') as mock_datetime:
        mock_datetime.datetime.utcnow.return_value = mock_now
        mock_datetime.timedelta = datetime.timedelta

        # Test quote symbol logic
        has_event, msg = check_upcoming_tier1_events("AUDGBP", threshold_hours=24.0)
        assert has_event
        assert "BOE Rate Decision" in msg
        assert "in 19.0h" in msg

def test_check_upcoming_tier1_events_usd_logic_non_6_char():
    # "USD": [(2, 14, 0, "FOMC Rate Decision"), (4, 8, 30, "Non-Farm Payrolls (NFP)"), ...]
    # Let's set time to Wed 1:00 PM (1 hour away from FOMC)
    mock_now = datetime.datetime(2023, 10, 11, 13, 0, 0)

    with patch('agents.risk_agent.datetime') as mock_datetime:
        mock_datetime.datetime.utcnow.return_value = mock_now
        mock_datetime.timedelta = datetime.timedelta

        # Test non 6 character symbol containing USD
        has_event, msg = check_upcoming_tier1_events("SPX500USD", threshold_hours=24.0)
        assert has_event
        assert "FOMC Rate Decision" in msg
        assert "in 1.0h" in msg

def test_check_upcoming_tier1_events_threshold_not_met():
    # Let's set time to Monday 12:00 PM (more than 24h away from Wed 2:00 PM FOMC)
    mock_now = datetime.datetime(2023, 10, 9, 12, 0, 0) # Monday

    with patch('agents.risk_agent.datetime') as mock_datetime:
        mock_datetime.datetime.utcnow.return_value = mock_now
        mock_datetime.timedelta = datetime.timedelta

        # Event is in ~50 hours
        has_event, msg = check_upcoming_tier1_events("USDJPY", threshold_hours=24.0)
        assert not has_event
        assert msg == ""
