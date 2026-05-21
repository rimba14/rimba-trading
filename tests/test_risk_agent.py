import sys
from unittest.mock import MagicMock

# Mock MetaTrader5 before importing
sys.modules['MetaTrader5'] = MagicMock()

import pytest
from agents.risk_agent import get_usd_rate

def test_get_usd_rate_usd():
    assert get_usd_rate("USD") == 1.0

def test_get_usd_rate_direct_rate():
    mt5_mock = sys.modules['MetaTrader5']

    def mock_symbol_info_tick(symbol):
        if symbol == "GBPUSD":
            tick = MagicMock()
            tick.bid = 1.25
            return tick
        return None

    mt5_mock.symbol_info_tick.side_effect = mock_symbol_info_tick

    assert get_usd_rate("GBP") == 1.25

def test_get_usd_rate_inverse_rate():
    mt5_mock = sys.modules['MetaTrader5']

    def mock_symbol_info_tick(symbol):
        if symbol == "USDJPY":
            tick = MagicMock()
            tick.bid = 150.0
            return tick
        return None

    mt5_mock.symbol_info_tick.side_effect = mock_symbol_info_tick

    assert get_usd_rate("JPY") == 1.0 / 150.0

def test_get_usd_rate_fallback():
    mt5_mock = sys.modules['MetaTrader5']
    mt5_mock.symbol_info_tick.return_value = None

    assert get_usd_rate("XYZ") == 1.0

def test_get_usd_rate_tick_zero_bid():
    mt5_mock = sys.modules['MetaTrader5']

    tick = MagicMock()
    tick.bid = 0.0
    mt5_mock.symbol_info_tick.return_value = tick

    assert get_usd_rate("ABC") == 1.0
