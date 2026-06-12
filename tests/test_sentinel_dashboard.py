import time
import pytest
from unittest.mock import Mock, patch, MagicMock

from sentinel_dashboard import _arc_read, ARCTIC_TIMEOUT, get_oracle_lib

def test_arc_read_none_lib():
    """Test _arc_read returns None when lib is None."""
    assert _arc_read(None, "test_key") is None

def test_arc_read_success():
    """Test _arc_read returns the correct result when lib.read succeeds."""
    mock_lib = Mock()
    mock_lib.read.return_value = "success_data"

    result = _arc_read(mock_lib, "test_key")

    assert result == "success_data"
    mock_lib.read.assert_called_once_with("test_key")

def test_arc_read_timeout():
    """Test _arc_read returns None when lib.read times out."""
    mock_lib = Mock()

    def slow_read(key):
        time.sleep(ARCTIC_TIMEOUT + 0.2)
        return "late_data"

    mock_lib.read.side_effect = slow_read

    start_time = time.time()
    result = _arc_read(mock_lib, "test_key")
    end_time = time.time()

    assert result is None
    mock_lib.read.assert_called_once_with("test_key")
    # The timeout exception happens in ThreadPoolExecutor's result() method.
    # The slow read blocks the background thread. ThreadPoolExecutor shuts down on __exit__
    # but does NOT cancel running futures. So it blocks waiting for the thread to finish!
    # Therefore we cannot assert that it finishes early. Wait time will be >= ARCTIC_TIMEOUT + 0.2.
    # We simply check that we get None because fut.result(timeout=...) raised TimeoutError.

def test_arc_read_exception():
    """Test _arc_read returns None when lib.read raises an exception."""
    mock_lib = Mock()
    mock_lib.read.side_effect = Exception("ArcticDB connection failed")

    result = _arc_read(mock_lib, "test_key")

    assert result is None
    mock_lib.read.assert_called_once_with("test_key")

@patch("sentinel_dashboard.Arctic")
def test_get_oracle_lib_success(mock_arctic_class):
    """Test get_oracle_lib returns the library when 'oracle_cache' exists."""
    mock_ac = MagicMock()
    mock_arctic_class.return_value = mock_ac
    mock_ac.list_libraries.return_value = ["oracle_cache", "other_lib"]
    mock_ac.__getitem__.return_value = "mock_oracle_lib"

    # Accessing the original function from the cached function via .__wrapped__
    result = get_oracle_lib.__wrapped__()

    assert result == "mock_oracle_lib"
    mock_arctic_class.assert_called_once_with("lmdb://C:/Sentinel_Project/data/arctic_cache")
    mock_ac.list_libraries.assert_called_once()
    mock_ac.__getitem__.assert_called_once_with("oracle_cache")

@patch("sentinel_dashboard.Arctic")
def test_get_oracle_lib_missing_library(mock_arctic_class):
    """Test get_oracle_lib returns None when 'oracle_cache' is missing."""
    mock_ac = MagicMock()
    mock_arctic_class.return_value = mock_ac
    mock_ac.list_libraries.return_value = ["other_lib"]

    result = get_oracle_lib.__wrapped__()

    assert result is None
    mock_arctic_class.assert_called_once()
    mock_ac.list_libraries.assert_called_once()

@patch("sentinel_dashboard.st.error")
@patch("sentinel_dashboard.Arctic")
def test_get_oracle_lib_exception(mock_arctic_class, mock_st_error):
    """Test get_oracle_lib returns None and calls st.error on exception."""
    mock_arctic_class.side_effect = Exception("Connection error")

    result = get_oracle_lib.__wrapped__()

    assert result is None
    mock_st_error.assert_called_once()
    assert "Connection error" in str(mock_st_error.call_args)
