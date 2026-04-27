import MetaTrader5 as mt5
import logging

# Configure Logging for Discovery
logging.basicConfig(level=logging.INFO, format='%(asctime)s [DISCOVERY] %(message)s')

# --- Risk Parameters ---
KELLY_FRACTION = 0.25    # Quarter-Kelly for drawdown protection
PORTFOLIO_HEAT_CAP = 0.20 # 20% max open risk
LEVERAGE_WALL = 10.0      # 10x Notional limit

# --- System Constants ---
STALENESS_THRESHOLD = 360 
ARCTIC_TIMEOUT = 0.3      

def get_valid_mt5_symbol(base_symbol):
    """
    Universal MT5 Symbol Discovery (v16.9): Dynamic matcher for broker suffixes.
    Attempts to map base symbols (e.g., BTCUSD) to exact tradeable strings.
    """
    # 1. Direct Match
    info = mt5.symbol_info(base_symbol)
    if info and info.visible: return base_symbol
    
    # 2. Suffix Matcher (Common suffixes: .m, .pro, .t, +, -)
    common_suffixes = [".m", ".pro", ".t", "+", "-", ".r"]
    for suffix in common_suffixes:
        test_sym = f"{base_symbol}{suffix}"
        info = mt5.symbol_info(test_sym)
        if info and info.visible: return test_sym

    # 3. Pattern Matcher (Discovery via all symbols)
    all_symbols = mt5.symbols_get()
    if all_symbols:
        for s in all_symbols:
            # Match if s.name contains base_symbol as prefix or part of it
            if base_symbol in s.name and len(s.name) <= len(base_symbol) + 5:
                return s.name
    return None

def resolve_watchlist(base_list):
    """Dynamically resolves a watchlist to tradeable symbols."""
    resolved = []
    for sym in base_list:
        v = get_valid_mt5_symbol(sym)
        if v: 
            resolved.append(v)
        else:
            logging.warning(f"Could not resolve tradeable symbol for {sym}")
    return resolved

# --- Initialize MT5 for Discovery Process ---
if not mt5.initialize():
    logging.error("MT5 Initialization failed in sentinel_config.py.")
    WATCHLIST = ["BTCUSD", "ETHUSD", "BCHUSD", "LTCUSD", "SOLUSD", "XRPUSD", "ADAUSD"]
else:
    BASE_WATCHLIST = [
        # Crypto (15)
        "BTCUSD", "ETHUSD", "BCHUSD", "LTCUSD", "SOLUSD", "XRPUSD", "ADAUSD", 
        "DOTUSD", "LINKUSD", "UNIUSD", "DOGEUSD", "MATICUSD", "AVAXUSD", "TRXUSD", "ATOMUSD",
        # Forex Majors & Minors (20)
        "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", 
        "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "NZDJPY", "GBPCAD", "EURCAD", 
        "CADJPY", "CADCHF", "CHFJPY", "EURAUD", "GBPNZD", "EURNZD",
        # Metals & Commodities (7)
        "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "WTI", "BRENT", "NATGAS",
        # Indices (14)
        "NAS100", "SP500", "DJ30", "GER40", "UK100", "FRA40", "HK50", 
        "EU50", "JPN225", "IT40", "ES35", "AU200", "CHINAA50", "US2000"
    ]
    WATCHLIST = resolve_watchlist(BASE_WATCHLIST)
    logging.info(f"Watchlist discovered: {len(WATCHLIST)} assets active.")

# --- System Constants (Legacy/Discovery) ---
MAGIC_NUMBER = 142
BROKER_SUFFIX = "" 
