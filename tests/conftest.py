import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock MetaTrader5 to avoid import errors on Linux
sys.modules['MetaTrader5'] = MagicMock()
