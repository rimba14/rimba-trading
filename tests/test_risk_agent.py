import sys
from unittest.mock import patch, MagicMock

# Mock MetaTrader5 before importing
sys.modules['MetaTrader5'] = MagicMock()

from agents.risk_agent import get_usd_rate

def test_get_usd_rate_usd():
    # When currency is USD, it should return 1.0 without calling MT5
    with patch('agents.risk_agent.mt5') as mock_mt5:
        rate = get_usd_rate('USD')
        assert rate == 1.0
        mock_mt5.symbol_info_tick.assert_not_called()

def test_get_usd_rate_direct():
    # Mocking a direct rate (e.g., EURUSD)
    with patch('agents.risk_agent.mt5') as mock_mt5:
        mock_tick = MagicMock()
        mock_tick.bid = 1.15

        # When looking for EURUSD it succeeds
        def side_effect(symbol):
            if symbol == 'EURUSD':
                return mock_tick
            return None

        mock_mt5.symbol_info_tick.side_effect = side_effect

        rate = get_usd_rate('EUR')
        assert rate == 1.15
        mock_mt5.symbol_info_tick.assert_called_with('EURUSD')

def test_get_usd_rate_inverse():
    # Mocking an inverse rate (e.g., USDJPY)
    with patch('agents.risk_agent.mt5') as mock_mt5:
        mock_tick = MagicMock()
        mock_tick.bid = 150.0

        # When looking for JPYUSD it fails, but USDJPY succeeds
        def side_effect(symbol):
            if symbol == 'USDJPY':
                return mock_tick
            return None

        mock_mt5.symbol_info_tick.side_effect = side_effect

        rate = get_usd_rate('JPY')
        assert rate == 1.0 / 150.0

def test_get_usd_rate_fallback():
    # When tick info is not available, it should fallback to 1.0
    with patch('agents.risk_agent.mt5') as mock_mt5:
        mock_mt5.symbol_info_tick.return_value = None

        rate = get_usd_rate('XYZ')
        assert rate == 1.0

def test_get_usd_rate_zero_bid_fallback():
    # When tick bid is 0, it should fallback to 1.0
    with patch('agents.risk_agent.mt5') as mock_mt5:
        mock_tick = MagicMock()
        mock_tick.bid = 0.0
        mock_mt5.symbol_info_tick.return_value = mock_tick

        rate = get_usd_rate('XYZ')
        assert rate == 1.0
