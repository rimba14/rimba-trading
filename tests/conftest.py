import sys
import os
sys.path.insert(0, os.path.abspath("."))
from unittest.mock import MagicMock
sys.modules['MetaTrader5'] = MagicMock()
sys.modules['fastapi_sniper'] = MagicMock()
