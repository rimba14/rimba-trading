import MetaTrader5 as mt5
import logging
import sys
import time

# Add project root to path to import sentinel_config
sys.path.append(r'C:\Sentinel_Project')
try:
    from sentinel_config import BASE_WATCHLIST, get_valid_mt5_symbol
except ImportError:
    BASE_WATCHLIST = [
        "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD", "BCHUSD", "XRPUSD", "ADAUSD", "DOTUSD",
        "MATICUSD", "DOGEUSD", "UNIUSD", "ATOMUSD", "TRXUSD",
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY",
        "EURCHF", "AUDJPY", "NZDJPY", "CHFJPY", "EURAUD", "GBPAUD", "USDMXN", "USDZAR", "USDTRY", "EURNOK",
        "EURSEK", "USDCNH", "USDSGD", "USDHKD", "EURPLN",
        "SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40", "XAUUSD", "XAGUSD", "CL-OIL"
    ]
    def get_valid_mt5_symbol(s): return s

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def recover_mt5():
    logging.info("Starting Phase 2: Terminal Synchronization")
    if not mt5.initialize():
        logging.error(f"mt5.initialize() failed: {mt5.last_error()}")
        return False
    
    logging.info("MT5 Initialized. Syncing Market Watch watchlist...")
    
    resolved_count = 0
    for base in BASE_WATCHLIST:
        # Try direct or resolved
        selected = False
        # Direct
        if mt5.symbol_select(base, True):
            selected = True
        else:
            # Try with common suffixes if get_valid_mt5_symbol is available
            try:
                res = get_valid_mt5_symbol(base)
                if res and mt5.symbol_select(res, True):
                    selected = True
            except:
                pass
        
        if selected:
            resolved_count += 1
            # logging.info(f"Synced: {base}")
        else:
            logging.warning(f"Failed to sync: {base}")
            
    logging.info(f"Phase 2 Complete: {resolved_count}/{len(BASE_WATCHLIST)} assets synced to Market Watch.")
    
    # Phase 4 Preview: Check specific assets
    for sym in ["BTCUSD", "US2000", "EURUSD"]:
        ticks = mt5.copy_ticks_from(sym, time.time(), 10, mt5.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 0:
            logging.info(f"Tick verification for {sym}: SUCCESS ({len(ticks)} ticks retrieved)")
        else:
            logging.warning(f"Tick verification for {sym}: FAILED (is the symbol selected?)")

    mt5.shutdown()
    return True

if __name__ == "__main__":
    recover_mt5()
