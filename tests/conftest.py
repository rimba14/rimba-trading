import sys
from unittest.mock import MagicMock

# Mock MetaTrader5 because it only installs on Windows
sys.modules['MetaTrader5'] = MagicMock()
