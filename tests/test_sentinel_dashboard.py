import time
import sys
from unittest.mock import Mock

# Mock MetaTrader5 and other dependencies before importing sentinel_dashboard
sys.modules['MetaTrader5'] = Mock()
sys.modules['arcticdb'] = Mock()

import pytest
from sentinel_dashboard import _arc_read, _arc_read_batch, ARCTIC_TIMEOUT

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


def test_arc_read_batch_none_lib():
    """Test _arc_read_batch returns a dict of Nones when lib is None."""
    keys = ["k1", "k2"]
    result = _arc_read_batch(None, keys)
    assert result == {"k1": None, "k2": None}


def test_arc_read_batch_success():
    """Test _arc_read_batch returns correct data for all keys."""
    mock_lib = Mock()
    mock_lib.read.side_effect = lambda k: f"data_{k}"

    keys = ["k1", "k2"]
    result = _arc_read_batch(mock_lib, keys)

    assert result == {"k1": "data_k1", "k2": "data_k2"}


def test_arc_read_batch_partial_timeout():
    """Test _arc_read_batch handles timeouts for some keys."""
    mock_lib = Mock()

    def slow_read(key):
        if key == "slow":
            time.sleep(ARCTIC_TIMEOUT + 0.2)
            return "late"
        return f"data_{key}"

    mock_lib.read.side_effect = slow_read

    keys = ["fast", "slow"]
    result = _arc_read_batch(mock_lib, keys)

    assert result["fast"] == "data_fast"
    assert result["slow"] is None


def test_arc_read_batch_exception():
    """Test _arc_read_batch handles exceptions for some keys."""
    mock_lib = Mock()

    def buggy_read(key):
        if key == "error":
            raise Exception("Fail")
        return f"data_{key}"

    mock_lib.read.side_effect = buggy_read

    keys = ["ok", "error"]
    result = _arc_read_batch(mock_lib, keys)

    assert result["ok"] == "data_ok"
    assert result["error"] is None
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
