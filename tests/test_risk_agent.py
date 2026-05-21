import pytest
from unittest.mock import patch, MagicMock
import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import check_upcoming_tier1_events

class MockDatetime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return cls.mock_utcnow

@pytest.fixture
def mock_datetime(monkeypatch):
    import agents.risk_agent
    monkeypatch.setattr(agents.risk_agent.datetime, 'datetime', MockDatetime)
    yield MockDatetime

def test_event_imminent(mock_datetime):
    # FOMC is Wednesday (day 2) at 14:00.
    # Set mock to Wed 12:00, which is 2 hours before the event.
    mock_datetime.mock_utcnow = datetime.datetime(2023, 11, 1, 12, 0, 0) # Nov 1, 2023 is Wednesday
    has_event, _ = check_upcoming_tier1_events("USDJPY", threshold_hours=24.0)
    assert has_event is True

def test_event_not_imminent(mock_datetime):
    # Set mock to Tue 12:00, which is 26 hours before the event.
    mock_datetime.mock_utcnow = datetime.datetime(2023, 10, 31, 12, 0, 0) # Oct 31, 2023 is Tuesday
    has_event, _ = check_upcoming_tier1_events("USDJPY", threshold_hours=24.0)
    assert has_event is False

def test_event_recently_passed(mock_datetime):
    # GBP has BOE Rate Decision on day 3 (Thu) at 7:00
    # Let's set time to Thu 8:00
    mock_datetime.mock_utcnow = datetime.datetime(2023, 11, 2, 8, 0, 0)
    has_event, _ = check_upcoming_tier1_events("GBPJPY", threshold_hours=24.0)
    assert has_event is False

def test_non_forex_symbol(mock_datetime):
    # AAPL Q3 Earnings is Thursday (day 3) at 16:00.
    # Set mock to Thu 15:00, which is 1 hour before the event.
    mock_datetime.mock_utcnow = datetime.datetime(2023, 11, 2, 15, 0, 0) # Nov 2, 2023 is Thursday
    has_event, _ = check_upcoming_tier1_events("AAPL", threshold_hours=24.0)
    assert has_event is True

def test_edge_case_base_quote(mock_datetime):
    # ECB Rate Decision is Wednesday (day 3) at 8:15 (actually Day 3 is Thursday!)
    # Let's set mock to Thu 8:00, which is 15 mins before the event.
    mock_datetime.mock_utcnow = datetime.datetime(2023, 11, 2, 8, 0, 0) # Nov 2, 2023 is Thursday
    has_event, _ = check_upcoming_tier1_events("EURAUD", threshold_hours=24.0)
    assert has_event is True
