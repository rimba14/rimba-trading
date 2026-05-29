"""
sentinel_config.py - ADAPTIVE SENTINEL CONFIGURATION & SYMBOL DISCOVERY (v19.2)
Constitution Article: Precision Isolation & Micro-Variance Scaling.
Phase 1-6 Architecture Online: Asynchronous Micro-Batching, 6-Decimal Precision, Z-Score Scaling.
Phase 4: Dynamic Optuna Injection (Gate, Kelly, Heat, Wall).
"""
import os
import json
import MetaTrader5 as mt5
import logging
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# v19.2 Directive: Dynamic Risk Parameter Injection (Optuna Bridge)
# If sentinel_hyperopt.py has generated new parameters, we inject them here.
PARAMS_PATH = Path(r"C:\Sentinel_Project\dynamic_risk_params.json")
DYN_PARAMS = {}
if PARAMS_PATH.exists():
    try:
        with open(PARAMS_PATH, "r") as f:
            DYN_PARAMS = json.load(f)
        logging.info(f"[CONFIG] Dynamic parameters injected from {PARAMS_PATH.name}")
    except Exception as e:
        logging.warning(f"[CONFIG] Failed to load dynamic parameters: {e}")

# Configure Logging for Discovery
logging.basicConfig(level=logging.INFO, format='%(asctime)s [DISCOVERY] %(message)s')

# RISK PARAMETERS (Phase 4 — Fractional Kelly & Absolute Risk Ceilings)
KELLY_FRACTION     = float(DYN_PARAMS.get("kelly_fraction", 0.25))
PORTFOLIO_HEAT_CAP = float(DYN_PARAMS.get("portfolio_heat_cap", 0.20))
HARD_RISK_CAP      = 0.02   # 2.0% per-trade absolute maximum
LEVERAGE_WALL      = 10.0   # 10× notional margin limit

# Phase 4 Gate Layer — v30.60
GATE_MAX_LEVERAGE          = 10.0
GATE_MAX_RISK_PCT_PER_TRADE = 0.02
GATE_MAX_PORTFOLIO_HEAT    = 0.20
GATE_BLACKOUT_FRIDAY_HOUR  = 23
GATE_BLACKOUT_FRIDAY_MIN   = 55
GATE_BLACKOUT_MONDAY_HOUR  = 0
GATE_BLACKOUT_MONDAY_MIN   = 15

# Dynamic Router
ROUTER_EQUITY_UPDATE_THRESHOLD = 50.0
ROUTER_LOG_PATH = "C:\\Sentinel_Project\\shap_diagnostics\\instrument_eligibility_{date}.json"

# ECN minimum lots — update when broker changes
GATE_ECN_MIN_LOTS = {
    "ETHUSD": 0.10, "BTCUSD": 0.01, "SOLUSD": 0.10,
    "NAS100": 0.10, "US500":  0.10, "US30":   0.10,
    "NGAS":   0.10, "COPPER": 0.10,    
    # Forex default: 0.01
}

# Minimum equity per instrument
GATE_MIN_EQUITY = {
    "ETHUSD": 0.0, "BTCUSD": 0.0, "NAS100": 0.0,
    "SOLUSD": 500.0,  "NGAS":   500.0,  "COPPER": 500.0,
}

# SYSTEM CONSTANTS (v19.2)
STALENESS_THRESHOLD = 900   # Hard 900 s signal staleness gate
ARCTIC_TIMEOUT      = 0.3   # Hard 300ms latency cap for ArcticDB (v19.1)
EPISTEMIC_GATE      = 0.8200  # v29.0: Swing Trading Epistemic Gate (0.82 threshold)
AC_LARGE_ORDER_THRESHOLD = 0.50 # v23.1: Minimum lot size for Almgren-Chriss slicing
REASONING_TIMEOUT   = int(os.getenv("REASONING_TIMEOUT", 45))

# PSR Reset Epoch (Phase 5 — SRE Reset v18.1)
# Only deals AFTER this timestamp contribute to the PSR calculation.
# Setting to 1746090457 (2025-05-01 09:07:37 UTC)
PSR_EPOCH = 1746090457

# [DEPRECATED v17.9] Ollama MoE RAM-lock — Local inference deprecated. Cloud-only architecture.
OLLAMA_KEEP_ALIVE   = -1  # Kept for legacy import compatibility only

# ---------------------------------------------------------------------------
# DUAL-ENGINE MODEL CONSTANTS (v17.9)
# ---------------------------------------------------------------------------
# Groq serves Crypto assets via high-speed LLM (Gemma as per v17.9 Constitution)
GROQ_GEMMA_MODEL   = os.getenv("GROQ_MODEL", "gemma2-9b-it")
# Gemini serves Forex and Indices (deep macro-synthesis engine)
GEMINI_MODEL_NAME  = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

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
    Three-phase fallback: direct -> suffix -> pattern scan.
    Strictly never hardcodes broker suffixes.
    """
    # Phase 1 — Direct match (pre-select to guarantee visibility if hidden)
    mt5.symbol_select(base_symbol, True)
    info = mt5.symbol_info(base_symbol)
    if info and info.visible:
        return base_symbol

    # Phase 2 — Common suffix probing
    for suffix in (".m", ".pro", ".t", "+", "-", ".r", ".c", ".x"):
        test_sym = f"{base_symbol}{suffix}"
        mt5.symbol_select(test_sym, True)
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
                mt5.symbol_select(s.name, True)
                return s.name

        # Priority 2: base symbol as prefix with short (<= 5-char) suffix
        for s in all_symbols:
            if s.name.upper().startswith(base_up) and len(s.name) <= len(base_symbol) + 5:
                mt5.symbol_select(s.name, True)
                return s.name

        # Priority 3: base symbol contained anywhere in the name
        for s in all_symbols:
            if base_up in s.name.upper():
                mt5.symbol_select(s.name, True)
                return s.name

    return None


def resolve_watchlist(base_list: list) -> list:
    """Dynamically resolves a watchlist of base symbols to tradeable MT5 strings."""
    resolved = []
    for sym in base_list:
        v = get_valid_mt5_symbol(sym)
        if v:
            mt5.symbol_select(v, True)
            resolved.append(v)
        else:
            logging.warning(f"[DISCOVERY] Could not resolve tradeable symbol for base: {sym}")
    return resolved


# ---------------------------------------------------------------------------
# WATCHLIST BOOTSTRAP (v19.5 — 50-Asset Expanded Universe)
# Asynchronous Micro-Batching (chunks of 10) enforced in Slow Loop.
# Dual-Engine routing:
#   Groq (Gemma)  -> CRYPTO (15 assets)
#   Gemini        -> FOREX, INDICES, COMMODITIES (35 assets)
# ---------------------------------------------------------------------------
BASE_WATCHLIST = [
    # Crypto (15)
    "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD", "BCHUSD", "XRPUSD", "ADAUSD", "DOTUSD",
    "MATICUSD", "DOGEUSD", "UNIUSD", "ATOMUSD", "TRXUSD",
    
    # Forex & Macro (25)
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "GBPJPY",
    "EURCHF", "AUDJPY", "NZDJPY", "CHFJPY", "EURAUD", "GBPAUD", "USDMXN", "USDZAR", "USDTRY", "EURNOK",
    "EURSEK", "USDCNH", "USDSGD", "USDHKD", "EURPLN",
    
    # Indices & Commodities (10)
    "SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40", "XAUUSD", "XAGUSD", "CL-OIL"
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


# v30.75 Consensus & Variance Safeguards
CONSENSUS_DIVERGENCE_THRESHOLD = 0.40
MIN_INFERENCE_AGENTS_REQUIRED  = 2
STAGNANT_VARIANCE_THRESHOLD    = 1e-7
