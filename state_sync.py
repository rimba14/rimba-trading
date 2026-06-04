import time
import sqlite3
import logging
from pathlib import Path
import MetaTrader5 as mt5

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("STATE_SYNC")

DB_PATH = Path.home() / ".hermes" / "state.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Active Positions Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS active_positions (
        ticket INTEGER PRIMARY KEY,
        symbol TEXT NOT NULL,
        direction INTEGER NOT NULL,
        size REAL NOT NULL,
        open_price REAL NOT NULL,
        sl_price REAL NOT NULL,
        tp_price REAL NOT NULL,
        epoch_timestamp INTEGER NOT NULL
    )
    ''')
    
    # Account Telemetry Table (Single row updated constantly)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS account_telemetry (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        balance REAL NOT NULL,
        equity REAL NOT NULL,
        floating_pnl REAL NOT NULL,
        current_margin REAL NOT NULL,
        peak_drawdown REAL NOT NULL
    )
    ''')
    
    # Initialize the single row for account_telemetry if not exists
    cursor.execute('''
    INSERT OR IGNORE INTO account_telemetry (id, balance, equity, floating_pnl, current_margin, peak_drawdown) 
    VALUES (1, 0.0, 0.0, 0.0, 0.0, 0.0)
    ''')
    
    conn.commit()
    conn.close()

def sync_loop():
    if not mt5.initialize():
        logger.error(f"MT5 Initialize Failed: {mt5.last_error()}")
        return

    logger.info("MT5 Connected. Starting State Sync Engine...")
    init_db()

    # To track peak drawdown manually locally across syncs
    peak_equity = 0.0
    
    # Connection that stays open for fast inserts
    conn = sqlite3.connect(DB_PATH, isolation_level=None) # autocommit
    cursor = conn.cursor()
    
    # Pragma for speed
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")

    try:
        while True:
            # 1. Fetch Account Info
            acc = mt5.account_info()
            if acc:
                balance = acc.balance
                equity = acc.equity
                margin = acc.margin
                floating_pnl = acc.profit
                
                # Calculate Peak Drawdown dynamically
                if equity > peak_equity:
                    peak_equity = equity
                drawdown = 0.0
                if peak_equity > 0:
                    drawdown = (peak_equity - equity) / peak_equity
                
                cursor.execute('''
                UPDATE account_telemetry 
                SET balance=?, equity=?, floating_pnl=?, current_margin=?, peak_drawdown=?
                WHERE id=1
                ''', (balance, equity, floating_pnl, margin, drawdown))

            # 2. Fetch Active Positions
            positions = mt5.positions_get()
            
            # Use transaction for atomic bulk insert
            cursor.execute("BEGIN TRANSACTION")
            # Clear old positions and re-insert the live state. 
            # (Because positions can be closed out-of-band by MT5 SL/TP or manual interventions)
            cursor.execute("DELETE FROM active_positions")
            
            if positions:
                for p in positions:
                    cursor.execute('''
                    INSERT INTO active_positions (ticket, symbol, direction, size, open_price, sl_price, tp_price, epoch_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (p.ticket, p.symbol, p.type, p.volume, p.price_open, p.sl, p.tp, p.time))
            cursor.execute("COMMIT")
            
            # Small sleep to prevent starving the CPU while keeping data near-real-time
            time.sleep(0.25)
            
    except KeyboardInterrupt:
        logger.info("State Sync Engine Shutdown gracefully.")
    finally:
        conn.close()
        mt5.shutdown()

if __name__ == "__main__":
    sync_loop()
