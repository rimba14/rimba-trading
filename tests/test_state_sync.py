import sys
from unittest.mock import MagicMock

# Mock MetaTrader5 before importing state_sync
mock_mt5 = MagicMock()
sys.modules['MetaTrader5'] = mock_mt5

import pytest
from unittest.mock import patch
import sqlite3
import state_sync
from dataclasses import dataclass

@dataclass
class MockPosition:
    ticket: int
    symbol: str
    type: int
    volume: float
    price_open: float
    sl: float
    tp: float
    time: int

def test_init_db(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("state_sync.DB_PATH", db_path):
        state_sync.init_db()
        assert db_path.exists()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='active_positions'")
        assert cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account_telemetry'")
        assert cursor.fetchone() is not None

        # Check initial row in account_telemetry
        cursor.execute("SELECT COUNT(*) FROM account_telemetry")
        assert cursor.fetchone()[0] == 1

        conn.close()

def test_sync_loop_iteration(tmp_path):
    db_path = tmp_path / "test.db"

    mock_positions = [
        MockPosition(101, "EURUSD", 0, 0.1, 1.1000, 1.0900, 1.1100, 123456789),
        MockPosition(102, "GBPUSD", 1, 0.2, 1.3000, 1.3100, 1.2900, 123456790)
    ]

    mock_acc = MagicMock()
    mock_acc.balance = 10000.0
    mock_acc.equity = 10100.0
    mock_acc.margin = 500.0
    mock_acc.profit = 100.0

    with patch("state_sync.mt5") as mocked_mt5, \
         patch("state_sync.DB_PATH", db_path), \
         patch("state_sync.time.sleep", side_effect=InterruptedError("Stop loop")):

        mocked_mt5.initialize.return_value = True
        mocked_mt5.account_info.return_value = mock_acc
        mocked_mt5.positions_get.return_value = mock_positions

        try:
            state_sync.sync_loop()
        except InterruptedError:
            pass # Expected to stop the loop

        # Verify DB content
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM active_positions ORDER BY ticket")
        rows = cursor.fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 101
        assert rows[0][1] == "EURUSD"
        assert rows[1][0] == 102
        assert rows[1][1] == "GBPUSD"

        cursor.execute("SELECT balance, equity FROM account_telemetry WHERE id=1")
        row = cursor.fetchone()
        assert row[0] == 10000.0
        assert row[1] == 10100.0

        conn.close()
