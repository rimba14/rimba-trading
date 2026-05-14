import MetaTrader5 as mt5
import logging
import os
import sys

# Add project root to sys.path
sys.path.append(r"C:\Sentinel_Project")
from sentinel_config import WATCHLIST

logging.basicConfig(level=logging.INFO)

def diag_mt5_visibility():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    print(f"Watchlist Size: {len(WATCHLIST)}")
    
    # Test indices: 0 (EURUSD.m usually), 1 (2nd), 49 (50th)
    test_indices = [0, 1, len(WATCHLIST)-1]
    
    for idx in test_indices:
        if idx >= len(WATCHLIST): continue
        symbol = WATCHLIST[idx]
        print(f"\n--- Testing Symbol [{idx}]: {symbol} ---")
        
        # 1. Check if selected
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"  [ERROR] symbol_info({symbol}) returned None.")
            # Try to select it
            if mt5.symbol_select(symbol, True):
                print(f"  [ACTION] Successfully selected {symbol} into Market Watch.")
                info = mt5.symbol_info(symbol)
            else:
                print(f"  [ERROR] Failed to select {symbol}. Check broker support.")
                continue
        else:
            print(f"  [OK] Symbol info found. Visible: {info.visible}")

        # 2. Attempt to pull 1 candle
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
        if rates is None or len(rates) == 0:
            print(f"  [ERROR] copy_rates_from_pos({symbol}) returned None or Empty.")
            # Try to see if it's a suffix issue?
            print(f"  [DIAG] Last error: {mt5.last_error()}")
        else:
            print(f"  [OK] Successfully pulled M1 candle. Price: {rates[0]['close']}")

    mt5.shutdown()

if __name__ == "__main__":
    diag_mt5_visibility()
