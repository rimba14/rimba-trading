import sys
from unittest.mock import MagicMock

# Mock MetaTrader5
mock_mt5 = MagicMock()
mock_mt5.SYMBOL_TRADE_MODE_DISABLED = 0
mock_mt5.ORDER_FILLING_IOC = 1
mock_mt5.ORDER_FILLING_FOK = 2
mock_mt5.ORDER_FILLING_RETURN = 3
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.ORDER_TIME_GTC = 0
mock_mt5.TRADE_RETCODE_DONE = 10009
sys.modules['MetaTrader5'] = mock_mt5

# Mock Arctic
mock_arctic = MagicMock()
sys.modules['arcticdb'] = mock_arctic
