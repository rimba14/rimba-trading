import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock MetaTrader5 before importing modules that use it
mock_mt5 = MagicMock()
sys.modules['MetaTrader5'] = mock_mt5

import gitagent_execute_sor as sor

@pytest.fixture
def mock_utils():
    with patch('gitagent_execute_sor.utils') as mock:
        mock.is_market_open.return_value = True
        mock.normalize_volume.side_effect = lambda sym, vol: vol
        yield mock

@pytest.fixture
def mock_sor_path():
    with patch('gitagent_execute_sor.get_sor_path') as mock:
        # Default: not synthetic
        mock.return_value = (False, [("EURUSD", 1)], 10, 10)
        yield mock

@pytest.fixture(autouse=True)
def reset_mock_mt5():
    mock_mt5.reset_mock()
    # Setup standard return values
    mock_mt5.TRADE_RETCODE_DONE = 10009
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
    mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.TRADE_ACTION_PENDING = 5
    mock_mt5.order_send.return_value.retcode = 10009
    yield

def test_execute_smart_order_direct(mock_utils, mock_sor_path):
    mock_mt5.symbol_info_tick.return_value.ask = 1.1000
    mock_mt5.symbol_info_tick.return_value.bid = 1.0990

    req = sor.TradeRequest(
        symbol="EURUSD",
        order_type=0, # BUY
        volume=0.1,
        sl=1.05,
        tp=1.15,
        comment="TestComment"
    )

    res = sor.execute_smart_order(req)

    assert res.retcode == 10009
    mock_mt5.order_send.assert_called_once()
    sent_request = mock_mt5.order_send.call_args[0][0]
    assert sent_request['symbol'] == "EURUSD"
    assert sent_request['volume'] == 0.1
    assert sent_request['sl'] == 1.05
    assert sent_request['tp'] == 1.15
    assert sent_request['comment'] == "TestComment"

def test_execute_smart_order_synthetic(mock_utils, mock_sor_path):
    # Mock synthetic path: EURUSD = EURGBP (BUY) + GBPUSD (BUY)
    mock_sor_path.return_value = (True, [("EURGBP", 0), ("GBPUSD", 0)], 5, 10)

    mock_mt5.symbol_info_tick.return_value.ask = 1.0
    mock_mt5.symbol_info_tick.return_value.bid = 1.0

    req = sor.TradeRequest(
        symbol="EURUSD",
        order_type=0, # BUY
        volume=0.1,
        comment="TestSynth"
    )

    results = sor.execute_smart_order(req)

    assert len(results) == 2
    assert all(r.retcode == 10009 for r in results)
    assert mock_mt5.order_send.call_count == 2

    # Verify first leg
    call1_args = mock_mt5.order_send.call_args_list[0][0][0]
    assert call1_args['symbol'] == "EURGBP"
    assert call1_args['comment'] == "TestSynth_leg"

    # Verify second leg
    call2_args = mock_mt5.order_send.call_args_list[1][0][0]
    assert call2_args['symbol'] == "GBPUSD"
    assert call2_args['comment'] == "TestSynth_leg"

def test_execute_standard_order_limit(mock_utils):
    mock_mt5.symbol_info_tick.return_value.ask = 1.1000
    mock_mt5.symbol_info_tick.return_value.bid = 1.0990

    req = sor.TradeRequest(
        symbol="EURUSD",
        order_type=2, # BUY_LIMIT
        volume=0.1,
        sl=1.05,
        tp=1.15,
        comment="LimitTest"
    )

    res = sor.execute_standard_order(req)

    assert res.retcode == 10009
    sent_request = mock_mt5.order_send.call_args[0][0]
    assert sent_request['action'] == 5 # PENDING
    assert sent_request['type'] == 2 # BUY_LIMIT
