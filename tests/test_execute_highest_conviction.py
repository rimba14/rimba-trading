import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import sys

# Mocking MetaTrader5 constants
mock_mt5 = MagicMock()
mock_mt5.TIMEFRAME_H1 = 16385
mock_mt5.SYMBOL_TRADE_MODE_DISABLED = 2
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.ORDER_FILLING_IOC = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_FILLING_FOK = 0
mock_mt5.ORDER_FILLING_RETURN = 2

mock_arctic = MagicMock()
sys.modules["MetaTrader5"] = mock_mt5
sys.modules["arcticdb"] = mock_arctic

import execute_highest_conviction

class TestExecuteHighestConviction(unittest.TestCase):
    def setUp(self):
        mock_mt5.reset_mock()
        # Restore constants after reset
        mock_mt5.TIMEFRAME_H1 = 16385
        mock_mt5.SYMBOL_TRADE_MODE_DISABLED = 2
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.ORDER_TYPE_SELL = 1
        mock_mt5.ORDER_FILLING_IOC = 1
        mock_mt5.TRADE_ACTION_DEAL = 1
        mock_mt5.ORDER_TIME_GTC = 0
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.ORDER_FILLING_FOK = 0
        mock_mt5.ORDER_FILLING_RETURN = 2
        mock_arctic.reset_mock()

    @patch("execute_highest_conviction.Arctic")
    @patch("execute_highest_conviction.mt5")
    @patch("execute_highest_conviction.sys.exit")
    def test_main_execution_flow(self, mock_exit, mock_mt5_in_main, mock_arctic_class):
        # Setup mocks
        mock_mt5_in_main.initialize.return_value = True
        mock_mt5_in_main.account_info.return_value = MagicMock(balance=10000.0)

        # Mock constants in the local mock too
        mock_mt5_in_main.ORDER_TYPE_BUY = 0
        mock_mt5_in_main.ORDER_TYPE_SELL = 1
        mock_mt5_in_main.TRADE_ACTION_DEAL = 1
        mock_mt5_in_main.ORDER_TIME_GTC = 0
        mock_mt5_in_main.ORDER_FILLING_IOC = 1
        mock_mt5_in_main.TRADE_RETCODE_DONE = 10009
        mock_mt5_in_main.TIMEFRAME_H1 = 16385

        # Mock ArcticDB
        mock_store = MagicMock()
        mock_arctic_class.return_value = mock_store
        mock_lib = MagicMock()
        mock_store.__getitem__.return_value = mock_lib

        mock_lib.list_symbols.return_value = ["EURUSD_meta"]
        meta_data = pd.DataFrame([{
            "meta_conviction": 0.8,
            "wasserstein_state": "TREND"
        }])
        mock_lib.read.return_value.data = meta_data

        # Mock MT5 symbol info
        mock_mt5_in_main.symbol_select.return_value = True
        mock_info = MagicMock()
        mock_info.trade_mode = 0
        mock_info.digits = 5
        mock_info.point = 0.00001
        mock_info.trade_tick_value = 1.0
        mock_info.trade_tick_size = 0.00001
        mock_info.volume_step = 0.01
        mock_info.volume_min = 0.01
        mock_info.volume_max = 100.0
        mock_mt5_in_main.symbol_info.return_value = mock_info

        mock_tick = MagicMock()
        mock_tick.ask = 1.1000
        mock_tick.bid = 1.0990
        mock_mt5_in_main.symbol_info_tick.return_value = mock_tick

        mock_mt5_in_main.positions_get.return_value = []

        # Mock rates for ATR
        rates = np.array([
            (0, 1.1000, 1.1010, 1.0990, 1.1005, 100, 0, 0)] * 20,
            dtype=[('time', '<i8'), ('open', '<f8'), ('high', '<f8'), ('low', '<f8'), ('close', '<f8'), ('tick_volume', '<u8'), ('spread', '<i4'), ('real_volume', '<u8')]
        )
        mock_mt5_in_main.copy_rates_from_pos.return_value = rates

        # Mock order_send result
        mock_result = MagicMock()
        mock_result.retcode = 10009 # mt5.TRADE_RETCODE_DONE
        mock_mt5_in_main.order_send.return_value = mock_result

        # Run main
        execute_highest_conviction.main()

        # Verify success
        mock_mt5_in_main.order_send.assert_called()
        args, kwargs = mock_mt5_in_main.order_send.call_args
        request = args[0]
        self.assertEqual(request["symbol"], "EURUSD")
        self.assertEqual(request["magic"], 777777)

if __name__ == "__main__":
    unittest.main()
