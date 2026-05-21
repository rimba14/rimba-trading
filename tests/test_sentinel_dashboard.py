import pytest
from unittest.mock import patch, MagicMock
import sys

# Mock MetaTrader5 before importing sentinel_dashboard
sys.modules['MetaTrader5'] = MagicMock()

from sentinel_dashboard import get_oracle_lib

@patch('sentinel_dashboard.st')
def test_get_oracle_lib_success(mock_st):
    with patch("sentinel_dashboard.Arctic") as mock_arctic:
        mock_ac = MagicMock()
        mock_arctic.return_value = mock_ac
        mock_ac.list_libraries.return_value = ["oracle_cache"]
        mock_lib = MagicMock()
        mock_ac.__getitem__.return_value = mock_lib

        # We might need to clear streamlit cache to test it properly
        get_oracle_lib.clear()

        result = get_oracle_lib()
        assert result == mock_lib
        mock_st.error.assert_not_called()

@patch('sentinel_dashboard.st')
def test_get_oracle_lib_missing_library(mock_st):
    with patch("sentinel_dashboard.Arctic") as mock_arctic:
        mock_ac = MagicMock()
        mock_arctic.return_value = mock_ac
        mock_ac.list_libraries.return_value = ["other_cache"]

        get_oracle_lib.clear()

        result = get_oracle_lib()
        assert result is None
        mock_st.error.assert_not_called()

@patch('sentinel_dashboard.st')
def test_get_oracle_lib_exception(mock_st):
    with patch("sentinel_dashboard.Arctic") as mock_arctic:
        mock_arctic.side_effect = Exception("Connection Failed")

        get_oracle_lib.clear()

        result = get_oracle_lib()
        assert result is None
        mock_st.error.assert_called_once_with("ArcticDB connection failed: Connection Failed")
