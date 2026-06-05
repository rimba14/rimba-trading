import MetaTrader5 as mt5
import os
import time
import json
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Directive: Phase 5 Firebase Signal Bridge

# Load environment
load_dotenv()
MAGIC_NUMBER = 142

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [LISTENER] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("LocalListener")

class MachineBListener:
    """
    v17.2 Machine B Execution Node (Local).
    Listens to signals and executes on MT5.
    """
    def __init__(self):
        if not mt5.initialize():
            logger.error("[FATAL] MT5 Initialization failed.")
            sys.exit(1)
        
        # Placeholder for Firebase Initialization
        # cred = credentials.Certificate("serviceAccountKey.json")
        # firebase_admin.initialize_app(cred, {
        #     'databaseURL': os.getenv("FIREBASE_DB_URL")
        # })
        # self.ref = db.reference('/signals')

    def execute_trade(self, signal):
        """Executes a trade on MT5 with Amnesia Lock and Risk Sanitization."""
        symbol = signal.get("symbol")
        direction = signal.get("direction")
        conviction = signal.get("conviction", 0.0)
        
        # 1. Amnesia Lock: Check for any existing positions for this symbol
        existing = mt5.positions_get(symbol=symbol, magic=MAGIC_NUMBER)
        if existing:
            # v17.3 Strict Mode: No hedging. One position max per asset.
            logger.warning(f"[{symbol}] Amnesia Lock: Position already exists. Blocking {direction} to prevent hedging.")
            return False

        # 2. Risk Sanitization (Fractional Kelly Sizing)
        # In v17.2, sizing is calculated on Machine A and passed in the signal
        # or calculated here based on local balance.
        acc = mt5.account_info()
        if not acc: return False
        
        # Simplified Sizing (v17.2 Small Account Bypass)
        lot = signal.get("lot", 0.01)
        if lot < 0.01: 
            lot = 0.01
            logger.warning(f"[{symbol}] Small Account Bypass triggered: Rounding up to 0.01.")

        # 3. Execution (Pure Virtual Stops - No SL/TP on broker)
        tick = mt5.symbol_info_tick(symbol)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": tick.ask if direction == "BUY" else tick.bid,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": f"v17.2_p{conviction:.2f}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[{symbol}] Trade Executed: {direction} {lot} lots @ {res.price}")
            return True
        else:
            logger.error(f"[{symbol}] Execution failed: {res.comment}")
            return False

    def signal_callback(self, event):
        """Callback for Firebase signal arrival."""
        if event.data:
            logger.info(f"New Signal Received: {event.data}")
            self.execute_trade(event.data)

    def listen_loop(self):
        logger.info("Machine B Listener Active (Awaiting Firebase Signals)...")
        # In a real Firebase setup, we'd use:
        # self.ref.listen(self.signal_callback)
        
        # Decoupled Action Queue (Phase 5)
        SIGNAL_QUEUE = Path("C:/Sentinel_Project/action_queue")
        os.makedirs(SIGNAL_QUEUE, exist_ok=True)
        
        while True:
            try:
                signals = list(SIGNAL_QUEUE.glob("*.json"))
                for sig_file in signals:
                    try:
                        with open(sig_file, 'r') as f:
                            signal = json.load(f)
                        # Execute and then ALWAYS remove the file to prevent logic loops
                        self.execute_trade(signal)
                        if os.path.exists(sig_file):
                            os.remove(sig_file)
                    except Exception as e:
                        logger.error(f"Error processing {sig_file.name}: {e}")
                        if os.path.exists(sig_file): os.remove(sig_file)
                time.sleep(1)
            except Exception as e:
                logger.error(f"Listener Error: {e}")
                time.sleep(5)

if __name__ == "__main__":
    listener = MachineBListener()
    try:
        listener.listen_loop()
    except KeyboardInterrupt:
        mt5.shutdown()
