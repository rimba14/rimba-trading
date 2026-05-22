import sys
import os
import unittest.mock as mock

mt5_mock = mock.MagicMock()
mt5_mock.ORDER_TYPE_BUY = 0
mt5_mock.ORDER_TYPE_SELL = 1
mt5_mock.TRADE_ACTION_DEAL = 1
mt5_mock.ORDER_TIME_GTC = 0
mt5_mock.ORDER_FILLING_IOC = 1
mt5_mock.TRADE_RETCODE_DONE = 10009
sys.modules['MetaTrader5'] = mt5_mock

sys.modules['git_arctic'] = mock.MagicMock()
sys.modules['gitagent_utils'] = mock.MagicMock()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents")))
from profit_manager_v15 import close_position, MAGIC_NUMBER

def test_close_position_no_tick():
    pos_mock = mock.MagicMock()
    pos_mock.symbol = "EURUSD"
    mt5_mock.symbol_info_tick.return_value = None

    result = close_position(pos_mock, "TEST")
    assert result is False
    mt5_mock.symbol_info_tick.assert_called_with("EURUSD")

def test_close_position_success():
    pos_mock = mock.MagicMock()
    pos_mock.symbol = "EURUSD"
    pos_mock.type = mt5_mock.ORDER_TYPE_BUY
    pos_mock.volume = 1.5
    pos_mock.ticket = 12345

    tick_mock = mock.MagicMock()
    tick_mock.bid = 1.1000
    tick_mock.ask = 1.1001
    mt5_mock.symbol_info_tick.return_value = tick_mock

    res_mock = mock.MagicMock()
    res_mock.retcode = mt5_mock.TRADE_RETCODE_DONE
    mt5_mock.order_send.return_value = res_mock

    result = close_position(pos_mock, "TEST_SUCCESS")
    assert result is True

    mt5_mock.order_send.assert_called_once()
    args, kwargs = mt5_mock.order_send.call_args
    request = args[0]

    assert request["action"] == mt5_mock.TRADE_ACTION_DEAL
    assert request["symbol"] == "EURUSD"
    assert request["volume"] == 1.5
    assert request["type"] == mt5_mock.ORDER_TYPE_SELL
    assert request["position"] == 12345
    assert request["price"] == tick_mock.bid
    assert request["comment"] == "Exit_TEST_SUCCESS"
    assert request["magic"] == MAGIC_NUMBER

def test_close_position_sell_success():
    mt5_mock.order_send.reset_mock()
    pos_mock = mock.MagicMock()
    pos_mock.symbol = "GBPUSD"
    pos_mock.type = mt5_mock.ORDER_TYPE_SELL
    pos_mock.volume = 2.0
    pos_mock.ticket = 54321

    tick_mock = mock.MagicMock()
    tick_mock.bid = 1.2000
    tick_mock.ask = 1.2005
    mt5_mock.symbol_info_tick.return_value = tick_mock

    res_mock = mock.MagicMock()
    res_mock.retcode = mt5_mock.TRADE_RETCODE_DONE
    mt5_mock.order_send.return_value = res_mock

    result = close_position(pos_mock, "TEST_SELL")
    assert result is True

    args, kwargs = mt5_mock.order_send.call_args
    request = args[0]
    assert request["type"] == mt5_mock.ORDER_TYPE_BUY
    assert request["price"] == tick_mock.ask

def test_close_position_failure():
    mt5_mock.order_send.reset_mock()
    pos_mock = mock.MagicMock()
    pos_mock.symbol = "USDJPY"
    pos_mock.type = mt5_mock.ORDER_TYPE_BUY
    pos_mock.volume = 1.0
    pos_mock.ticket = 99999

    tick_mock = mock.MagicMock()
    tick_mock.bid = 150.00
    mt5_mock.symbol_info_tick.return_value = tick_mock

    res_mock = mock.MagicMock()
    res_mock.retcode = 10013 # Invalid request
    mt5_mock.order_send.return_value = res_mock

    result = close_position(pos_mock, "TEST_FAIL")
    assert result is False
