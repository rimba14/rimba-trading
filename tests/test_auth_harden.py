import os
import pytest
import requests
import time
from multiprocessing import Process
import uvicorn
from unittest.mock import MagicMock
import sys

# Mock MetaTrader5 before importing fastapi_sniper
mock_mt5 = MagicMock()
sys.modules["MetaTrader5"] = mock_mt5
mock_mt5.initialize.return_value = True
mock_mt5.terminal_info.return_value = MagicMock(connected=True, trade_allowed=True)
mock_mt5.symbols_get.return_value = []
mock_mt5.symbol_select.return_value = True
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1

# Mock other dependencies that might cause issues in the sandbox
sys.modules["sentinel_config"] = MagicMock()
sys.modules["capital_wall"] = MagicMock()
sys.modules["monitor_sentinel"] = MagicMock()

from fastapi_sniper import app

BASE_URL = "http://127.0.0.1:8005"

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8005)

@pytest.fixture(scope="module", autouse=True)
def server():
    # Set a dummy API key for testing
    os.environ["SENTINEL_API_KEY"] = "test-secret-key"
    os.environ["SENTINEL_DRY_FIRE"] = "1"

    proc = Process(target=run_server, daemon=True)
    proc.start()
    time.sleep(2)  # Wait for server to start
    yield
    proc.terminate()

def test_execute_trade_no_key():
    payload = {"symbol": "EURUSD", "direction": "BUY"}
    resp = requests.post(f"{BASE_URL}/execute_trade", json=payload)
    assert resp.status_code == 403
    assert "Invalid API Key" in resp.text or "Forbidden" in resp.text

def test_execute_trade_wrong_key():
    payload = {"symbol": "EURUSD", "direction": "BUY"}
    headers = {"X-API-Key": "wrong-key"}
    resp = requests.post(f"{BASE_URL}/execute_trade", json=payload, headers=headers)
    assert resp.status_code == 403

def test_execute_trade_correct_key():
    # Dry-fire mode should return success if auth passes
    payload = {
        "symbol": "EURUSD",
        "direction": "BUY",
        "conviction": 0.85,
        "wasserstein_state": "TREND",
        "timestamp": int(time.time()),
        "signal_type": "MOMENTUM"
    }
    headers = {"X-API-Key": "test-secret-key"}
    resp = requests.post(f"{BASE_URL}/execute_trade", json=payload, headers=headers)
    # We might get a 406 or other Veto, but it shouldn't be 403 Forbidden
    assert resp.status_code != 403

def test_liquidate_no_key():
    payload = {"symbol": "EURUSD", "ticket": 12345}
    resp = requests.post(f"{BASE_URL}/liquidate", json=payload)
    assert resp.status_code == 403

def test_liquidate_correct_key():
    payload = {"symbol": "EURUSD", "ticket": 12345, "reason": "Test"}
    headers = {"X-API-Key": "test-secret-key"}
    resp = requests.post(f"{BASE_URL}/liquidate", json=payload, headers=headers)
    assert resp.status_code != 403

def test_strip_stops_no_key():
    payload = {"ticket": 12345}
    resp = requests.post(f"{BASE_URL}/strip_stops", json=payload)
    assert resp.status_code == 403

def test_status_unprotected():
    resp = requests.get(f"{BASE_URL}/status")
    assert resp.status_code == 200
