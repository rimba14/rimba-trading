import sys
from unittest.mock import MagicMock

# The root codebase relies on Windows-only MetaTrader5. Mock it for tests in Linux environments.
sys.modules['MetaTrader5'] = MagicMock()
