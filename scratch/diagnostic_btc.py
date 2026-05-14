import os
import sys
import logging
import MetaTrader5 as mt5
from pathlib import Path
import traceback

# Add project root to sys.path
sys.path.append(r"C:\Sentinel_Project")

import sentinel_slow_loop
import gitagent_sigproc as sigproc

def run_btc_deepdive():
    logging.info("Starting Deep Inference Audit: BTCUSD")
    
    # Initialize MT5
    if not mt5.initialize():
        logging.error("MT5 Initialization failed")
        return

    symbol = "BTCUSD"
    
    # Ensure symbol is selected
    mt5.symbol_select(symbol, True)
    mt5.symbol_info_tick(symbol)

    # Check tick counts via sigproc
    try:
        df = sigproc.get_tick_dataframe(symbol, 2000)
        if df is None:
            logging.error(f"sigproc.get_tick_dataframe returned None for {symbol}")
        else:
            logging.info(f"Ticks for {symbol}: {len(df)}")
            logging.info(f"NaN Count in raw dataframe: {df.isna().sum().sum()}")
    except Exception:
        logging.error(f"Error in sigproc.get_tick_dataframe:\n{traceback.format_exc()}")

    # Force oracle update
    logging.info(f"Executing sentinel_slow_loop.update_slow_oracles('{symbol}', force_refresh=True)...")
    try:
        sentinel_slow_loop.update_slow_oracles(symbol, force_refresh=True)
    except Exception as e:
        logging.error(f"CRITICAL: Exception caught in update_slow_oracles for {symbol}:\n{traceback.format_exc()}")

    mt5.shutdown()
    logging.info("Deep Inference Audit: BTCUSD Complete")

if __name__ == "__main__":
    # Setup basic logging to stdout with more detail
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    run_btc_deepdive()
