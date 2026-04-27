import sys
import os
import logging
import MetaTrader5 as mt5

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import sentinel_slow_loop

logging.basicConfig(level=logging.INFO, format='%(asctime)s [TEST] %(message)s')

def test_single_cycle():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    symbol = "EURUSD"
    print(f"\n--- TRIGGERING ORACLE AUDIT FOR {symbol} ---")
    sentinel_slow_loop.update_slow_oracles(symbol)
    print("--- AUDIT COMPLETE ---\n")
    mt5.shutdown()

if __name__ == "__main__":
    test_single_cycle()
