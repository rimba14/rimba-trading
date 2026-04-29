"""
sentinel_config.py - ADAPTIVE SENTINEL CONFIGURATION & SYMBOL DISCOVERY (v17.3)
Constitution Article: Symbol Auto-Discovery, Risk Parameters, UTC Constants.
"""
import os
import MetaTrader5 as mt5
import logging
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure Logging for Discovery
logging.basicConfig(level=logging.INFO, format='%(asctime)s [DISCOVERY] %(message)s')

# ---------------------------------------------------------------------------
# RISK PARAMETERS (Phase 4 — Fractional Kelly & Absolute Risk Ceilings)
# ---------------------------------------------------------------------------
KELLY_FRACTION   = 0.25   # Quarter-Kelly for drawdown protection
PORTFOLIO_HEAT_CAP = 0.20  # 20% max open risk (portfolio heat)
HARD_RISK_CAP    = 0.02   # 2.0% per-trade absolute maximum
LEVERAGE_WALL    = 10.0   # 10× notional margin limit

# ---------------------------------------------------------------------------
# SYSTEM CONSTANTS (v17.3)
# ---------------------------------------------------------------------------
STALENESS_THRESHOLD = 900   # Hard 900 s signal staleness gate
ARCTIC_TIMEOUT      = 0.3   # 300 ms latency cap for ArcticDB reads/writes
EPISTEMIC_GATE      = 0.82  # Absolute minimum meta-conviction threshold
REASONING_TIMEOUT   = int(os.getenv("REASONING_TIMEOUT", 45))  # Ollama API timeout (env-driven)

# Ollama MoE RAM-lock directive (keep_alive: -1 means lock forever)
OLLAMA_KEEP_ALIVE   = -1

# ---------------------------------------------------------------------------
# ASSET CLASS DEFINITIONS (Weekend Blackout & Regime Routing)
# ---------------------------------------------------------------------------
CRYPTO_BASE_SYMBOLS = {
    "BTCUSD","ETHUSD","BCHUSD","LTCUSD","SOLUSD","XRPUSD","ADAUSD",
    "DOTUSD","LINKUSD","UNIUSD","DOGEUSD","MATICUSD","AVAXUSD","TRXUSD","ATOMUSD"
}

# ---------------------------------------------------------------------------
# SYMBOL AUTO-DISCOVERY (Phase 1 — Fallback Base-Symbol Matcher)
# ---------------------------------------------------------------------------

def get_valid_mt5_symbol(base_symbol: str) -> str | None:
    """
    Universal MT5 Symbol Discovery (v17.3): Dynamic matcher for broker suffixes.
    Three-phase fallback: direct → suffix → pattern scan.
    Strictly never hardcodes broker suffixes.
    """
    # Phase 1 — Direct match
    info = mt5.symbol_info(base_symbol)
    if info and info.visible:
        return base_symbol

    # Phase 2 — Common suffix probing
    for suffix in (".m", ".pro", ".t", "+", "-", ".r", ".c", ".x"):
        test_sym = f"{base_symbol}{suffix}"
        info = mt5.symbol_info(test_sym)
        if info and info.visible:
            return test_sym

    # Phase 3 — Full scan with priority ordering
    all_symbols = mt5.symbols_get()
    if all_symbols:
        base_up = base_symbol.upper()

        # Priority 1: exact case-insensitive name match
        for s in all_symbols:
            if s.name.upper() == base_up:
                return s.name

        # Priority 2: base symbol as prefix with short (<= 5-char) suffix
        for s in all_symbols:
            if s.name.upper().startswith(base_up) and len(s.name) <= len(base_symbol) + 5:
                return s.name

        # Priority 3: base symbol contained anywhere in the name
        for s in all_symbols:
            if base_up in s.name.upper():
                return s.name

    return None


def resolve_watchlist(base_list: list) -> list:
    """Dynamically resolves a watchlist of base symbols to tradeable MT5 strings."""
    resolved = []
    for sym in base_list:
        v = get_valid_mt5_symbol(sym)
        if v:
            resolved.append(v)
        else:
            logging.warning(f"[DISCOVERY] Could not resolve tradeable symbol for base: {sym}")
    return resolved


# ---------------------------------------------------------------------------
# WATCHLIST BOOTSTRAP (v17.7 — 13-Asset Core Liquid List)
# Pruned from 56-asset load to stabilise 429 Too Many Requests errors.
# Dual-Engine split: Gemini → first 7 assets, Groq → remaining 6 assets.
# ---------------------------------------------------------------------------
BASE_WATCHLIST = [
    # Forex Majors (6)
    "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "NZDUSD",
    # Crypto (2)
    "BTCUSD", "ETHUSD",
    # Indices (3)
    "SP500", "NAS100", "GER40",
    # Metals (2)
    "XAUUSD", "XAGUSD",
]

if not mt5.initialize():
    logging.error("[DISCOVERY] MT5 Initialization failed. Using unresolved base watchlist as fallback.")
    WATCHLIST = list(BASE_WATCHLIST)
else:
    WATCHLIST = resolve_watchlist(BASE_WATCHLIST)
    logging.info(f"[DISCOVERY] Watchlist resolved: {len(WATCHLIST)}/{len(BASE_WATCHLIST)} assets active.")

# ---------------------------------------------------------------------------
# LEGACY / EXECUTION CONSTANTS
# ---------------------------------------------------------------------------
MAGIC_NUMBER  = 142
BROKER_SUFFIX = ""   # Never set manually — always use get_valid_mt5_symbol()
