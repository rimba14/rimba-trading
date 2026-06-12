import sys
import os
from unittest.mock import MagicMock

# Mock MetaTrader5 for Linux environments
sys.modules['MetaTrader5'] = MagicMock()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
