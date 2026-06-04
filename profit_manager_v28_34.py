"""
profit_manager_v28_34.py — SENTINEL PROFIT MANAGER v28.34 (Composite HMM Health Matrix)
═══════════════════════════════════════════════════════════════════════════════
Architecture: PositionState Registry | OracleCache | ExitScoreEngine
              ScaleOutCoordinator | R-Multiple PSR | Equity-Inclusive Drawdown
              Execution Deduplication | Fortress Trail (not retrace)
              TP Modification Bug Fixed | Broker Stop Armor on All SL Paths

Changelog vs v23.2:
  [CRITICAL FIX] TP modification now correctly sends target_tp, not pos.tp
  [CRITICAL FIX] Fortress Mode trails toward current_price, not back to entry−ATR
  [CRITICAL FIX] Scale-outs use current live volume, preventing over-close
  [CRITICAL FIX] Regime liquidation now has profit-weighted gate (won't kill +3R in 15s)
  [CRITICAL FIX] Drawdown uses account equity (includes open unrealized P&L)
  [SERIOUS FIX]  PSR uses normalized % returns per trade (not raw $P&L)
  [SERIOUS FIX]  Velocity kill requires 5-sample window + profit protection gate
  [SERIOUS FIX]  Breakeven SL passes through normalize_stop (prevents MT5 10016)
  [ARCH FIX]     PositionState dataclass replaces 6 scattered global dicts
  [ARCH FIX]     OracleCache — single ArcticDB read per symbol per cycle
  [ARCH FIX]     State cleanup on position close (prevents ticket reuse bugs)
  [ARCH FIX]     Execution deduplication flag (no double-close vs Machine B)
  [ARCH FIX]     ExitScoreEngine — weighted multi-dimensional scoring replaces
                 8 independent binary flags
  [ARCH FIX]     Naked sweep ATR is instrument-aware (price_floor + broker_floor)
  [ARCH FIX]     PSR minimum sample raised from 10 → 25
  [ARCH FIX]     HMM NEUTRAL/RANGING states explicitly handled (no silent passthrough)
"""

from __future__ import annotations

import MetaTrader5 as mt5
from tp_placement_engine import (
    TPPlacementEngine,
    TPValidationResult,
    StructuralLevelResolver,
    ASSET_CLASS_TIME_STOP,
    AssetClass,
)

import io, json, logging, os, re, socket, sys, time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import threading
import signal
from gitagent_types import TelemetryState

import numpy as np
import requests
from dotenv import load_dotenv
from scipy import stats

from agents.risk_agent import check_upcoming_tier1_events

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────
MAGIC_NUMBER            = 142
MAGIC_LEGACY            = 17300
MAGIC_TOP5              = 777777
PSR_THRESHOLD           = 0.80
PSR_EPOCH               = 1778483123        # v19.2 Phase 5 SRE Reset
PSR_MIN_SAMPLES         = 25               # [FIX] was 10 — statistically meaningless
WEBHOOK_URL             = os.getenv("DISCORD_WEBHOOK_URL")
DIAG_DIR                = Path("C:/Sentinel_Project/pending_diagnostics")
LOG_DIR                 = Path(r"C:\sentinel_logs")
ARCTIC_DIR              = "lmdb://C:/Sentinel_Project/data/arctic_cache"
REGIME_POLL_INTERVAL    = 5.0              # seconds between oracle reads per symbol
LIQUIDATION_COOLDOWN_S  = 60.0
EXIT_SCORE_THRESHOLD    = 0.60             # weighted score gate for cognitive exits
MAX_HOLDING_DAYS        = 10

for d in (DIAG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PROFIT_MANAGER] %(message)s",
    force=True,
    handlers=[
        logging.StreamHandler(
            io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        ),
        logging.FileHandler(
            str(LOG_DIR / "profit_manager_v25_0.log"), encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger("ProfitManager")


# ══════════════════════════════════════════════════════════════════════════════
#  SHOCK DETECTOR & FAILSAFE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════
from enum import Enum

class FailsafeAction(Enum):
    MARKET_CLOSE = "MARKET_CLOSE"
    TIGHTEN_SL = "TIGHTEN_SL"

class FailsafeSignal:
    def __init__(self, ticket: int, symbol: str, action: FailsafeAction, trigger: str):
        self.ticket = ticket
        self.symbol = symbol
        self.action = action
        self.trigger = trigger

SHOCK_DETECTOR_CONFIG = {
    "canary_assets": ["BTCUSD", "SP500", "GBPJPY"]
}

def _get_cluster(symbol: str) -> str:
    s = symbol.upper()
    crypto_keys = {"BTC", "ETH", "SOL", "AVAX", "LINK", "LTC", "BCH", "XRP", "ADA", "DOT", "MATIC", "DOGE", "UNI", "ATOM", "TRX"}
    if any(k in s for k in crypto_keys):
        return "RISK_ON_CRYPTO"
    
    equity_keys = {"SP500", "NAS100", "US30", "GER40", "HK50", "US2000", "FRA40", "UK100", "JPN225", "STOXX50"}
    if any(k in s for k in equity_keys):
        return "RISK_ON_EQUITY"
        
    commodity_keys = {"XAU", "XAG", "OIL", "CL-OIL", "XPT", "XPD", "GAS", "NGAS", "COPPER"}
    if any(k in s for k in commodity_keys):
        return "COMMODITIES"
        
    risk_on_fx_keys = {"GBPJPY", "EURJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY", "USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "EURAUD", "GBPAUD"}
    if any(k in s for k in risk_on_fx_keys):
        return "RISK_ON_FX"
        
    return "RISK_OFF"

def check_correlation_shock() -> bool:
    canaries = SHOCK_DETECTOR_CONFIG["canary_assets"]
    for asset in canaries:
        from sentinel_config import get_valid_mt5_symbol
        resolved = get_valid_mt5_symbol(asset)
        if not resolved:
            resolved = asset
        mt5.symbol_select(resolved, True)
        rates = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_H1, 0, 3)
        if rates is not None and len(rates) >= 3:
            close_now = float(rates[-1]['close'])
            close_prev = float(rates[-3]['close'])
            if close_prev > 0:
                change = (close_now - close_prev) / close_prev
                if change <= -0.012:
                    logger.warning(f"[SHOCK_DETECTOR] Canary shock detected on {resolved}: {change:.2%}")
                    return True
    return False

# --- CONSTRAINT 5: POOR-PERFORMANCE REMOVAL (LowProfitPairs) ---
_LOW_PROFIT_SUSPENDED_PAIRS = set()
_COOLDOWN_LOCKS = {} # symbol -> timestamp until blocked

def update_low_profit_pairs_tracker(closed_positions: list[dict]):
    global _LOW_PROFIT_SUSPENDED_PAIRS
    # Rolling metrics tracker over last 20 trades per pair
    pair_trades = defaultdict(list)
    for pos in closed_positions:
        pair_trades[pos["symbol"]].append(pos)
        
    for symbol, trades in pair_trades.items():
        if len(trades) < 5:
            continue
        recent = trades[:20]
        wins = sum(1 for t in recent if t.get("profit", 0) > 0)
        win_rate = wins / len(recent)
        net_pnl = sum(t.get("profit", 0) for t in recent)
        
        # Threshold: win-rate < 30% or net_pnl severely negative
        if win_rate < 0.30 or net_pnl < -100.0:
            if symbol not in _LOW_PROFIT_SUSPENDED_PAIRS:
                _LOW_PROFIT_SUSPENDED_PAIRS.add(symbol)
                logger.critical(f"[LOW_PROFIT_PAIRS] {symbol} suspended due to poor performance! WinRate={win_rate:.2f}, NetPnl={net_pnl:.2f}. Alerting SRE registry.")
                notify(f"**LOW PROFIT PAIRS ALERT**\n{symbol} suspended due to poor performance (WinRate={win_rate:.2f}, NetPnl={net_pnl:.2f}).")
        else:
            if symbol in _LOW_PROFIT_SUSPENDED_PAIRS and win_rate >= 0.40 and net_pnl > -50.0:
                _LOW_PROFIT_SUSPENDED_PAIRS.remove(symbol)
                logger.info(f"[LOW_PROFIT_PAIRS] {symbol} rehabilitated and restored to trading.")
                
    # Save to disk for capital_wall / sniper
    try:
        with open("C:/Sentinel_Project/data/low_profit_pairs.json", "w") as f:
            json.dump(list(_LOW_PROFIT_SUSPENDED_PAIRS), f)
    except Exception as e:
        logger.warning(f"Failed to save low profit pairs: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  INSTRUMENT CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════
_CRYPTO_KEYS    = {"BTC","ETH","SOL","XRP","ADA","DOT","LINK","AVAX","LTC","BCH","TRX","DOGE"}
_INDEX_KEYS     = {"SP500","US2000","GER40","US500","US30","NAS100","UK100","JPN225","FRA40","AUS200","STOXX50"}
_COMMODITY_KEYS = {"XAU","XAG","OIL","CL-OIL","XPT","XPD","GAS","NGAS"}
_JPY_PAIRS      = {"USDJPY","GBPJPY","EURJPY","AUDJPY","NZDJPY","CHFJPY","CADJPY"}


def classify_symbol(symbol: str) -> str:
    s = symbol.upper()
    if any(k in s for k in _CRYPTO_KEYS):    return "CRYPTO"
    if any(k in s for k in _INDEX_KEYS):     return "INDEX"
    if any(k in s for k in _COMMODITY_KEYS): return "COMMODITY"
    return "FOREX"


def calculate_institutional_hard_stop(current_price: float, is_buy: bool, atr: float, hmm_state: str) -> float:
    high_vol_states = {"HIGH-VOLATILITY", "CRISIS TAIL", "HIGH-VOL MEAN REVERSION"}
    med_vol_states = {"TRENDING", "BULL", "BEAR"}
    
    if hmm_state in high_vol_states:
        multiplier = 4.5
    elif hmm_state in med_vol_states:
        multiplier = 3.0
    else:
        multiplier = 2.0
        
    distance = atr * multiplier
    
    if is_buy:
        return current_price - distance
    else:
        return current_price + distance


def get_atr_multipliers(symbol: str, hmm_state: str) -> tuple[float, float]:
    """Returns (SL_mult, TP_mult) adjusted for asset class and HMM regime."""
    asset = classify_symbol(symbol)
    base_sl, base_tp = {
        "INDEX":     (4.0, 8.0),
        "CRYPTO":    (4.0, 8.0),
        "COMMODITY": (4.0, 8.0),
        "FOREX":     (6.0, 12.0),
    }.get(asset, (3.0, 6.0))

    if hmm_state == "BULL":
        base_sl *= 0.85;  base_tp *= 1.15
    elif hmm_state == "BEAR":
        base_sl *= 1.15;  base_tp *= 0.85
    # NEUTRAL / RANGING / CHOPPY → no adjustment (no silent passthrough bug)
    return base_sl, base_tp


def get_decay_rules(symbol: str, config: dict) -> dict:
    rules   = config.get("thesis_decay_rules", {})
    asset   = classify_symbol(symbol)
    defaults = {
        "CRYPTO":    {"min_hold_hours": 6,  "decay_threshold": 0.40},
        "INDEX":     {"min_hold_hours": 8,  "decay_threshold": 0.45},
        "COMMODITY": {"min_hold_hours": 12, "decay_threshold": 0.42},
        "FOREX":     {"min_hold_hours": 12, "decay_threshold": 0.42},
    }
    return rules.get(asset, defaults.get(asset, {"min_hold_hours": 12, "decay_threshold": 0.42}))


# ══════════════════════════════════════════════════════════════════════════════
#  POSITION STATE REGISTRY  [ARCH FIX] replaces 6+ scattered global dicts
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class PositionState:
    """Per-position mutable state. Single source of truth. GC'd when position closes."""
    ticket:           int
    symbol:           str
    direction:        int          # 0=BUY, 1=SELL
    entry_price:      float
    entry_time:       int
    entry_conviction: float = 0.50
    entry_tf:         str   = "H4"
    entry_atr:        float = 0.0  # ATR anchored on first oracle read
    strategy_type:    str   = "MOMENTUM"
    initial_sl:       float = 0.0

    # Scale-out coordinator: fractions are of the ORIGINAL entry volume
    zone1_done:        bool  = False   # +1.5 ATR → 35%
    zone2_done:        bool  = False   # +2.5 ATR → 35%
    divergence_done:   bool  = False   # conviction-weak scale → 50%
    event_horizon_done: bool = False   # pre-event scale → 50%
    scaled_fraction:   float = 0.0    # cumulative fraction closed so far

    # Conviction tracking
    last_conviction_update: float = 0.0

    # Regime gate
    regime_conflict_count: int = 0

    current_conviction:     float = 0.50
    current_conviction:     float = 0.50
    telemetry_logger:       Any   = None

    # Execution deduplication [ARCH FIX]
    liquidation_sent:    bool  = False
    last_liquidation_ts: float = 0.0

    # Peak tracking
    peak_price:    float = 0.0
    peak_profit_r: float = 0.0

    def is_buy(self) -> bool:
        return self.direction == 0

    def profit_delta(self, current_price: float) -> float:
        """Raw price movement in favour of the trade."""
        return (current_price - self.entry_price) if self.is_buy() else (self.entry_price - current_price)

    def profit_r(self, current_price: float, atr: float, sl_mult: float) -> float:
        """Unrealized profit expressed in R-multiples."""
        risk = atr * sl_mult
        if risk <= 0:
            return 0.0
        return self.profit_delta(current_price) / risk


# ══════════════════════════════════════════════════════════════════════════════
#  ORACLE DATA CACHE  [ARCH FIX] one ArcticDB read per symbol per cycle
# ══════════════════════════════════════════════════════════════════════════════
class OracleCache:
    def __init__(self, ttl: float = REGIME_POLL_INTERVAL):
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._ttl   = ttl

    def get(self, symbol: str) -> Optional[dict]:
        entry = self._cache.get(symbol)
        if entry and (time.time() - entry[0]) < self._ttl:
            return entry[1]
        data = _fetch_oracle_raw(symbol)
        self._cache[symbol] = (time.time(), data)
        return data

    def invalidate(self, symbol: str):
        self._cache.pop(symbol, None)

    def get_atr(self, symbol: str, timeframe: str, period: int, max_age_seconds: int) -> Optional[float]:
        import MetaTrader5 as mt5
        import numpy as np
        tf_map = {"D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1}
        tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_D1)
        bars = mt5.copy_rates_from_pos(symbol, tf, 0, period + 1)
        if bars is None or len(bars) < period:
            return None
        tr = []
        for i in range(1, len(bars)):
            h, l, prev_c = bars[i]['high'], bars[i]['low'], bars[i-1]['close']
            tr.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        return float(np.mean(tr))

    def get_bars(self, symbol: str, timeframe: str, count: int) -> Optional[list[dict]]:
        import MetaTrader5 as mt5
        tf_map = {"D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1}
        tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_D1)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None: return None
        return [{"time": r['time'], "open": r['open'], "high": r['high'], "low": r['low'], "close": r['close']} for r in rates]

    def get_hmm_state(self, symbol: str) -> str:
        data = self.get(symbol)
        return data["hmm_state"] if data else "RANGE"

    def get_wasserstein_distance(self, symbol: str) -> Optional[float]:
        data = self.get(symbol)
        if data and "wasserstein_distance" in data.get("raw_row", {}):
            return float(data["raw_row"]["wasserstein_distance"])
        return None


def _fetch_oracle_raw(symbol: str) -> Optional[dict]:
    """Single ArcticDB read — returns all oracle fields at once."""
    try:
        from arcticdb import Arctic
        store = Arctic(ARCTIC_DIR)
        lib   = store["oracle_cache"]
        item  = lib.read(f"{symbol}_meta")
        row   = item.data.iloc[-1]
        return {
            "hmm_state":  str(row["hmm_state"]),
            "conviction": float(row["meta_conviction"]),
            "atr":        float(row["atr"]),
            "entropy":    float(row.get("entropy", 0.0)),
            "strategy_type": str(row.get("strategy_type", "MOMENTUM")),
            "volatility_ratio": float(row.get("volatility_ratio", 1.0)),
            "ofi_velocity": float(row.get("ofi_velocity", 0.0)),
            "raw_row":    row,          # available for TF-specific conviction lookups
        }
    except Exception as e:
        logger.warning(f"[ORACLE_ERR] {symbol}: {e}")
        return None


def get_conviction_for_tf(oracle: dict, entry_tf: str) -> float:
    """Extract timeframe-specific conviction from already-fetched oracle dict."""
    try:
        row = oracle.get("raw_row")
        if row is not None:
            key = f"conviction_{entry_tf.lower()}"
            if key in row:
                return float(row[key])
        return oracle.get("conviction", 0.50)
    except Exception:
        return oracle.get("conviction", 0.50)


# ══════════════════════════════════════════════════════════════════════════════
#  ATR — INSTRUMENT-SAFE [ARCH FIX] crypto/index-aware floor
# ══════════════════════════════════════════════════════════════════════════════
def calculate_atr_d1(symbol: str, period: int = 14) -> float:
    """v30.98: Structural ATR uses D1 timeframe ONLY. H1/M15 ATR is PROHIBITED for SL placement."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, period + 1)
    if rates is None or len(rates) < period + 1:
        return 0.0
    h, lo, cl = rates["high"], rates["low"], rates["close"]
    tr = np.array([
        max(h[i+1] - lo[i+1], abs(h[i+1] - cl[i]), abs(lo[i+1] - cl[i]))
        for i in range(period)
    ])
    return float(np.mean(tr))


def get_safe_atr(symbol: str, oracle_atr: float, pos_open: float) -> float:
    """
    v30.98 instrument-safe ATR using D1 timeframe.
    BUG FIX v25.0: raw_atr=0.0010 was a hardcoded forex value — useless for BTCUSD/indices.
    BUG FIX v30.98: Changed from H1 to D1 ATR. H1 ATR produced SL 6-12x too tight.
    Three floors: D1 computed, 0.20% of price, broker stop level.
    """
    d1_atr      = calculate_atr_d1(symbol)
    price_floor = pos_open * 0.002          # 0.20% of open price
    info        = mt5.symbol_info(symbol)
    tick        = mt5.symbol_info_tick(symbol)
    broker_floor = (info.trade_stops_level * info.point * 3) if info else 0.0
    spread_floor = ((tick.ask - tick.bid) * 1.5) if tick and (tick.ask - tick.bid) > 0 else 0.0
    
    candidates  = [v for v in [d1_atr, oracle_atr, price_floor, broker_floor, spread_floor] if v > 0]
    return max(candidates) if candidates else 1e-5


# ══════════════════════════════════════════════════════════════════════════════
#  EQUITY-INCLUSIVE DRAWDOWN  [CRITICAL FIX] was closed-deals only
# ══════════════════════════════════════════════════════════════════════════════
_GLOBAL_PEAK_EQUITY = 0.0
_PEAK_TO_TROUGH_HALT_ACTIVE = False
MAX_DRAWDOWN_CEILING = 0.15 # 15% strict constitutional volatility ceiling

def get_equity_drawdown() -> tuple[float, float]:
    """
    v25.0: Uses account.equity which includes all open unrealized P&L.
    CONSTRAINT 6: PEAK-TO-TROUGH EQUITY CURVE DRAWDOWN GUARDIAN
    """
    global _GLOBAL_PEAK_EQUITY, _PEAK_TO_TROUGH_HALT_ACTIVE
    acc = mt5.account_info()
    if not acc:
        return 0.0, 0.0
    try:
        current_equity = float(acc.equity)
        
        # Track global maximum peak equity
        if current_equity > _GLOBAL_PEAK_EQUITY:
            _GLOBAL_PEAK_EQUITY = current_equity
            
        if _GLOBAL_PEAK_EQUITY > 0:
            drawdown = (_GLOBAL_PEAK_EQUITY - current_equity) / _GLOBAL_PEAK_EQUITY
        else:
            drawdown = 0.0
            
        # Peak-to-Trough Drawdown Guardian Logic
        if drawdown >= MAX_DRAWDOWN_CEILING and not _PEAK_TO_TROUGH_HALT_ACTIVE:
            _PEAK_TO_TROUGH_HALT_ACTIVE = True
            logger.critical(f"[DRAWDOWN_GUARDIAN] Peak-to-Trough DD crossed {drawdown:.2%} >= {MAX_DRAWDOWN_CEILING:.2%}! Executing fail-closed sequence. Halting position originations.")
            notify(f"**DRAWDOWN GUARDIAN TRIGGERED**\nGlobal DD: {drawdown:.2%}. Fail-closed sequence activated.")
        elif drawdown < (MAX_DRAWDOWN_CEILING * 0.8) and _PEAK_TO_TROUGH_HALT_ACTIVE:
            _PEAK_TO_TROUGH_HALT_ACTIVE = False
            logger.info(f"[DRAWDOWN_GUARDIAN] Equity recovered. DD: {drawdown:.2%}. Normal operations resuming.")
            
        return max(0.0, drawdown), current_equity
    except Exception:
        return 0.0, float(getattr(acc, "equity", 0.0))

# ══════════════════════════════════════════════════════════════════════════════
#  BROKER STOP ARMOR  (unified — all SL/TP paths go through this)
# ══════════════════════════════════════════════════════════════════════════════
def normalize_stop(
    symbol: str, current_price: float, target: float, is_sl: bool, is_buy: bool
) -> float:
    """
    v25.0: Single armor function for all SL/TP modifications.
    BUG FIX: Breakeven lock in v23.2 skipped this → MT5 10016 errors.
    """
    info = mt5.symbol_info(symbol)
    if not info:
        return target

    tick      = mt5.symbol_info_tick(symbol)
    spread    = (tick.ask - tick.bid) if (tick and tick.ask > tick.bid) else info.spread * info.point
    if spread <= 0:
        spread = 2 * info.point

    min_dist  = info.trade_stops_level * info.point
    safe_pad  = min_dist + spread + 2 * info.point

    if is_buy:
        target = min(target, current_price - safe_pad) if is_sl else max(target, current_price + safe_pad)
    else:
        target = max(target, current_price + safe_pad) if is_sl else min(target, current_price - safe_pad)

    if info.trade_tick_size > 0:
        target = round(target / info.trade_tick_size) * info.trade_tick_size
    return round(target, info.digits)


# ══════════════════════════════════════════════════════════════════════════════
#  EXIT SCORE ENGINE  [ARCH FIX] replaces 8 binary flags with weighted scoring
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ExitSignal:
    score:          float = 0.0
    hard_exit:      bool  = False   # bypasses score gate entirely
    reason_primary: str   = ""
    reasons:        list  = field(default_factory=list)


def _check_crypto_rules(
    ps: PositionState,
    symbol: str,
    is_buy: bool,
    hmm: str,
    pos_dir: str,
    h1_candles: int,
    live_p: float
) -> Optional[ExitSignal]:
    """Handles crypto-specific stagnation, thesis decay, and regime inversion."""
    crypto_keywords = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK", "AVAX", "LTC", "BCH", "TRX", "DOGE"}
    is_crypto = any(k in symbol.upper() for k in crypto_keywords)
    
    if not is_crypto:
        return None

    # Stagnation Exit (Barrier 3)
    if h1_candles > 120 and not ps.zone2_done:
        sig = ExitSignal()
        sig.hard_exit = True
        sig.reason_primary = "[STAGNATION LIQUIDATION]"
        sig.reasons.append(f"Crypto open > 120 bars ({h1_candles}) without hitting Zone 2")
        return sig

    # Thesis Decay
    thesis_p_crypto = live_p if is_buy else (1.0 - live_p)
    if thesis_p_crypto < 0.55:
        sig = ExitSignal()
        sig.hard_exit = True
        sig.reason_primary = "[THESIS DECAY] Conviction < 0.55"
        sig.reasons.append(f"Kronos Conviction {thesis_p_crypto:.3f} < 0.55")
        return sig
            
    # Regime Inversion
    if (is_buy and hmm == "BEAR") or (not is_buy and hmm == "BULL"):
        ps.regime_conflict_count += 1
        if ps.regime_conflict_count >= 3:
            sig = ExitSignal()
            sig.hard_exit = True
            sig.reason_primary = "[THESIS DECAY] Regime Inversion"
            sig.reasons.append(f"Regime flipped to {hmm} against {pos_dir} position for 3 periods")
            return sig
    else:
        ps.regime_conflict_count = 0
    return None


def _check_failsafe_rules(
    ps: PositionState,
    current_price: float,
    macro_atr: float,
    sl_mult: float,
    is_buy: bool
) -> Optional[ExitSignal]:
    """Handles broker execution failure (overshooting SL/TP)."""
    buffer = macro_atr * 0.10
    sl_target = (ps.entry_price - sl_mult * macro_atr) if is_buy else (ps.entry_price + sl_mult * macro_atr)
    tp_target = (ps.entry_price + sl_mult * 2.0 * macro_atr) if is_buy else (ps.entry_price - sl_mult * 2.0 * macro_atr)
    if ps.initial_sl > 0:
        sl_target = ps.initial_sl

    if (is_buy and current_price <= (sl_target - buffer)) or (not is_buy and current_price >= (sl_target + buffer)):
        sig = ExitSignal()
        sig.hard_exit = True
        sig.reason_primary = "[FAILSAFE TRIGGERED] Broker Execution Failure"
        sig.reasons.append(f"Price={current_price:.5f} blew past SL={sl_target:.5f} by buffer={buffer:.5f}")
        return sig

    if (is_buy and current_price >= (tp_target + buffer)) or (not is_buy and current_price <= (tp_target - buffer)):
        sig = ExitSignal()
        sig.hard_exit = True
        sig.reason_primary = "[FAILSAFE TRIGGERED] Broker Execution Failure"
        sig.reasons.append(f"Price={current_price:.5f} blew past TP={tp_target:.5f} by buffer={buffer:.5f}")
        return sig
    return None


def _check_macro_shock_rules(pos_dir: str, sentiment: float) -> Optional[ExitSignal]:
    """Handles sentiment-based hard exits."""
    if (pos_dir == "BUY" and sentiment < -0.65) or (pos_dir == "SELL" and sentiment > 0.65):
        sig = ExitSignal()
        sig.hard_exit = True
        sig.reason_primary = "[MACRO SHOCK]"
        sig.reasons.append(f"Sentiment={sentiment:.2f} threshold breached for {pos_dir}")
        return sig
    return None


def _score_regime_conflict(ps: PositionState, pos_dir: str, hmm: str, profit_r: float) -> tuple[float, Optional[str]]:
    """Calculates the regime conflict score component."""
    is_conflict = (pos_dir == "BUY" and hmm == "BEAR") or (pos_dir == "SELL" and hmm == "BULL")
    if is_conflict:
        ps.regime_conflict_count += 1
        # Higher profit → require more persistent regime conflict before exiting
        r_gate      = max(3, int(3 + max(0, profit_r)))   # 0R→3, 3R→6, 5R→8 confirms
        persistence = min(ps.regime_conflict_count / r_gate, 1.0)
        score = 0.40 * persistence
        reason = f"REGIME({hmm} vs {pos_dir}, count={ps.regime_conflict_count}/{r_gate})"
        return score, reason
    else:
        ps.regime_conflict_count = 0
        return 0.0, None


def _apply_hysteresis(
    symbol: str,
    current_price: float,
    ps: PositionState,
    elapsed: float,
    score: float,
    reasons: list[str]
) -> tuple[float, list[str]]:
    """Handles exit suppression based on age and profit delta."""
    if score <= 0:
        return score, reasons

    if elapsed < 1200:
        logger.info(f"[HARD_HOLD] {symbol}: suppressing exit — age {elapsed:.0f}s < 20m")
        return 0.0, [f"SUPPRESSED_HARD_HOLD({elapsed:.0f}s)"]

    info = mt5.symbol_info(symbol)
    if info:
        min_edge = 30 * info.point
        if ps.profit_delta(current_price) > -min_edge:
            logger.info(f"[HYSTERESIS] {symbol}: suppressing exit — profit delta > -30 points")
            return 0.0, [f"SUPPRESSED_MIN_EDGE({ps.profit_delta(current_price):.5f} > -{min_edge:.5f})"]

    return score, reasons


def _apply_event_horizon_gate(symbol: str, score: float, reasons: list[str]) -> tuple[float, list[str]]:
    """Handles exit suppression before Tier 1 events."""
    if score <= 0:
        return score, reasons

    try:
        has_event, event_desc = check_upcoming_tier1_events(symbol, threshold_hours=12.0)
        if has_event:
            logger.info(f"[EVENT_HORIZON_GATE] {symbol}: suppressing cognitive exits — {event_desc}")
            return 0.0, [f"SUPPRESSED_PRE_EVENT({event_desc})"]
    except Exception as e:
        logger.warning(f"[EVENT_CHECK_ERR] {symbol}: {e}")

    return score, reasons


def _apply_profit_dampening(profit_r: float, score: float) -> float:
    """Dampens exit scores for high-profit positions."""
    if profit_r > 2.0 and score > 0:
        dampener  = max(0.30, 1.0 - (profit_r - 2.0) * 0.08)
        return score * dampener
    return score


def compute_exit_score(
    ps:               PositionState,
    oracle:           dict,
    current_price:    float,
    macro_atr:        float,
    sl_mult:          float,
    live_p:           float,
    config:           dict,
    sentiment:        float,
    broker_now:       int,
    h1_candles:       int,
    is_weekend_pause: bool,
) -> ExitSignal:
    """
    v25.0 Exit Score Engine.

    Design principles:
    1. Hard exits (VSL, VTP, macro shock, velocity) bypass scoring entirely.
    2. Soft exits (regime, decay, dead-money, theta) are weighted and summed.
    3. Profit dampening: positions in strong profit require higher score to exit.
    4. Event Horizon suppresses all soft exits pre-event.
    5. Velocity kill requires 5-sample window + profit protection gate.
       BUG FIX: v23.2 used 3-tick window and had no profit protection.
    """
    sig     = ExitSignal()
    symbol  = ps.symbol
    is_buy  = ps.is_buy()
    hmm     = oracle.get("hmm_state", "NEUTRAL")
    pos_dir = "BUY" if is_buy else "SELL"

    profit_r = ps.profit_r(current_price, macro_atr, sl_mult)
    elapsed  = broker_now - ps.entry_time

    # ── 1. Crypto Triple-Barrier Rules (HARD EXIT) ───────────────────────────
    crypto_sig = _check_crypto_rules(ps, symbol, is_buy, hmm, pos_dir, h1_candles, live_p)
    if crypto_sig:
        return crypto_sig

    # ── 2. Secondary Failsafe (Broker Execution Failure) (HARD EXIT) ─────────
    failsafe_sig = _check_failsafe_rules(ps, current_price, macro_atr, sl_mult, is_buy)
    if failsafe_sig:
        return failsafe_sig

    # ── 3. Macro Shock / Sentiment Kill (HARD EXIT) ──────────────────────────
    macro_sig = _check_macro_shock_rules(pos_dir, sentiment)
    if macro_sig:
        return macro_sig

    # ── From here: soft scored exits ─────────────────────────────────────────

    # ── 4. Regime Conflict (scored) ──────────────────────────────────────────
    regime_score, regime_reason = _score_regime_conflict(ps, pos_dir, hmm, profit_r)
    sig.score += regime_score
    if regime_reason:
        sig.reasons.append(regime_reason)

    # ── 5. Hysteresis Hardening (v9.5) ──────────────────────────────────────────
    sig.score, sig.reasons = _apply_hysteresis(symbol, current_price, ps, elapsed, sig.score, sig.reasons)

    # ── 6. Event Horizon suppression gate ────────────────────────────────────
    sig.score, sig.reasons = _apply_event_horizon_gate(symbol, sig.score, sig.reasons)

    # ── 7. Profit-weighted dampening ─────────────────────────────────────────
    sig.score = _apply_profit_dampening(profit_r, sig.score)

    if sig.score > 0 and not sig.hard_exit:
        sig.reason_primary = f"[SCORED_EXIT score={sig.score:.2f}]"

    return sig


# ══════════════════════════════════════════════════════════════════════════════
#  SCALE-OUT COORDINATOR  [CRITICAL FIX] volume-safe partial closes
# ══════════════════════════════════════════════════════════════════════════════
def safe_scale_out(
    pos, ps: PositionState, fraction: float, tag: str,
    info, tick
) -> bool:
    """
    v25.0 volume-safe scale-out.
    BUG FIX: v23.2 computed close_vol from pos.volume (original), not current volume.
    Zone1 (35%) + Zone2 (35%) + Divergence (50%) could sum to 120% of original.
    Now: uses live pos.volume and validates remaining >= min_lot before executing.
    """
    vol_step = info.volume_step if (info and info.volume_step > 0) else 0.01
    min_vol  = info.volume_min  if (info and info.volume_min  > 0) else 0.01

    current_vol = pos.volume            # live volume from current MT5 snapshot
    close_vol   = round((current_vol * fraction) / vol_step) * vol_step
    close_vol   = max(close_vol, min_vol)
    remaining   = current_vol - close_vol

    if remaining < min_vol:
        logger.info(
            f"[SCALE_SKIP] {ps.symbol} #{ps.ticket}: "
            f"remaining={remaining:.3f} < min_vol={min_vol:.3f} — skipping partial close."
        )
        return False

    close_type  = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    close_price = tick.bid             if pos.type == 0 else tick.ask

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       ps.symbol,
        "volume":       float(close_vol),
        "type":         close_type,
        "position":     ps.ticket,
        "price":        close_price,
        "deviation":    30,
        "magic":        MAGIC_NUMBER,
        "comment":      tag[:31],
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        ps.scaled_fraction += fraction
        logger.info(
            f"[SCALE_OK] {ps.symbol} #{ps.ticket}: closed {close_vol:.3f} lots "
            f"({tag}). Total scaled: {ps.scaled_fraction:.0%}"
        )
        return True
    code = res.retcode if res else "N/A"
    msg  = res.comment if res else ""
    logger.warning(f"[SCALE_FAIL] {ps.symbol} #{ps.ticket}: retcode={code} {msg}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  EXECUTION LAYER
# ══════════════════════════════════════════════════════════════════════════════
def push_exit_signal(pos, reason: str):
    """Push exit to Machine B (Execution Node). Non-blocking."""
    url = os.getenv("EXECUTION_ENDPOINT_URL")
    if not url:
        logger.error("[EXIT_SIGNAL] EXECUTION_ENDPOINT_URL not configured.")
        return
    payload = {
        "action": "CLOSE", "symbol": pos.symbol, "ticket": pos.ticket,
        "reason": reason,  "timestamp": int(time.time()),
    }
    try:
        resp = requests.post(f"{url}/liquidate", json=payload, timeout=5)
        if resp.status_code == 200:
            logger.info(f"[EXIT_SIGNAL_OK] {pos.symbol} #{pos.ticket} → Execution Node")
        else:
            logger.error(f"[EXIT_SIGNAL_FAIL] {pos.symbol}: HTTP {resp.status_code}")
    except Exception as e:
        import traceback
        logger.error(f"[EXIT_SIGNAL_ERR] {pos.symbol}: {e}\n{traceback.format_exc()}")


def market_close(pos, reason: str = "PM_LIQUIDATION") -> bool:
    """Direct market close. Returns True on success."""
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        logger.error(f"[CLOSE_ERR] No tick for {pos.symbol}")
        return False

    close_type  = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    close_price = tick.bid             if pos.type == 0 else tick.ask

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       pos.symbol,
        "volume":       pos.volume,
        "type":         close_type,
        "position":     pos.ticket,
        "price":        close_price,
        "deviation":    30,
        "magic":        MAGIC_NUMBER,
        "comment":      reason[:31],
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"[CLOSED] {pos.symbol} #{pos.ticket} | PnL={pos.profit:+.2f} | {reason}")
        
        # CONSTRAINT 5: INSTANT REVENGE-TRADE COOLDOWN
        # If asset hits hard virtual stop-loss or is closed in drawdown, lock down for N bars (e.g., 2 hours = 7200s)
        if pos.profit < 0.0:
            cooldown_period = 7200
            _COOLDOWN_LOCKS[pos.symbol] = time.time() + cooldown_period
            logger.warning(f"[COOLDOWN_LOCK] {pos.symbol} closed in drawdown. Initiating Instant Revenge-Trade Cooldown for {cooldown_period}s.")
            try:
                with open("C:/Sentinel_Project/data/cooldown_locks.json", "w") as f:
                    json.dump(_COOLDOWN_LOCKS, f)
            except Exception as e:
                pass
                
        return True
    code = res.retcode if res else "N/A"
    msg  = res.comment if res else ""
    logger.error(f"[CLOSE_FAIL] {pos.symbol} #{pos.ticket}: {code} {msg}")
    return False


def notify(msg: str):
    if not WEBHOOK_URL:
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg}, timeout=8)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  PSR AUDITOR  [SERIOUS FIX] normalized % returns, not raw $ P&L
# ══════════════════════════════════════════════════════════════════════════════
def _deal_to_return(deal) -> Optional[float]:
    """
    Normalize deal profit to a % return for PSR.
    BUG FIX: v23.2 used raw dollar P&L — lot size changes corrupted the Sharpe distribution.
    v25.0: profit / notional_value → comparable across position sizes.
    """
    try:
        if deal.volume <= 0 or deal.price <= 0:
            return None
        info = mt5.symbol_info(deal.symbol)
        if not info or info.trade_contract_size <= 0:
            return None
        notional = deal.volume * deal.price * info.trade_contract_size
        return deal.profit / notional if notional > 0 else None
    except Exception:
        return None


def calculate_psr(returns: list[float]) -> float:
    """Bailey & Lopez de Prado PSR on normalized returns."""
    arr = np.array(returns)
    if len(arr) < PSR_MIN_SAMPLES:   # [FIX] was 10 — now 25
        return 1.0                    # insufficient data — no halt
    sharpe  = np.mean(arr) / (np.std(arr) + 1e-9)
    n       = len(arr)
    skew    = stats.skew(arr)
    kurt    = stats.kurtosis(arr)
    std_err = np.sqrt(
        (1 - skew * sharpe + (kurt - 1) / 4.0 * sharpe**2) / max(n - 1, 1)
    )
    return float(stats.norm.cdf(sharpe / (std_err + 1e-9)))


def load_risk_config() -> dict:
    try:
        with open("dynamic_risk_params.json", "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        logger.warning(f"[CONFIG_ERR] {e}")
        return {}


def _parse_entry_tf(comment: str) -> str:
    m = re.search(r"_TF([A-Za-z0-9]+)", comment or "")
    return m.group(1) if m else "H4"


def _parse_entry_conviction(comment: str) -> float:
    m = re.search(r"_P(0\.\d+)", comment or "")
    return float(m.group(1)) if m else 0.50


def _parse_strategy_type(comment: str, default: str = "MOMENTUM") -> str:
    if not comment:
        return default
    if "_MR_" in comment or "MEAN_REVERSION" in comment:
        return "MEAN_REVERSION"
    if "_MO_" in comment or "MOMENTUM" in comment:
        return "MOMENTUM"
    return default


# ══════════════════════════════════════════════════════════════════════════════
#  SENTINEL PROFIT MANAGER  v25.0
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  COMPOSITE THREE-METRIC HMM HEALTH MATRIX (v28.34)
# ══════════════════════════════════════════════════════════════════════════════

def get_entry_meta_from_db(symbol: str, entry_time: float) -> tuple[str, float]:
    try:
        from arcticdb import Arctic
        store = Arctic(ARCTIC_DIR)
        lib = store["oracle_cache"]
        # Try to read symbol_meta
        item = lib.read(f"{symbol}_meta")
        df = item.data
        # Find row closest to and before entry_time
        df_subset = df[df["timestamp"] <= entry_time]
        if not df_subset.empty:
            row = df_subset.iloc[-1]
            return str(row.get("hmm_state", "NEUTRAL")), float(row.get("atr", 0.0010))
    except Exception:
        pass
    return "NEUTRAL", 0.0010

def _deal_to_return_dict(pos: dict) -> float | None:
    try:
        info = mt5.symbol_info(pos["symbol"])
        if not info or info.trade_contract_size <= 0:
            return None
        notional = pos["volume"] * pos["entry_price"] * info.trade_contract_size
        return pos["profit"] / notional if notional > 0 else None
    except Exception:
        return None

def get_trailing_closed_positions(limit: int = 50) -> list[dict]:
    import MetaTrader5 as mt5
    from datetime import datetime, timedelta
    now = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(now - timedelta(days=30), now)
    if not deals:
        return []
    
    # Group deals by position_id
    positions_deals = defaultdict(list)
    for d in deals:
        if d.magic in (MAGIC_NUMBER, MAGIC_LEGACY, MAGIC_TOP5):
            positions_deals[d.position_id].append(d)
            
    closed_positions = []
    for pid, d_list in positions_deals.items():
        # A position is closed if the net volume is zero or there's an ENTRY_OUT deal
        in_deals = [d for d in d_list if d.entry == mt5.DEAL_ENTRY_IN]
        out_deals = [d for d in d_list if d.entry == mt5.DEAL_ENTRY_OUT]
        
        if in_deals and out_deals:
            out_deals.sort(key=lambda x: x.time)
            in_deals.sort(key=lambda x: x.time)
            
            entry_deal = in_deals[0]
            exit_deal = out_deals[-1]
            
            total_profit = sum(d.profit for d in out_deals)
            direction = entry_deal.type
            
            closed_positions.append({
                "ticket": pid,
                "symbol": entry_deal.symbol,
                "direction": direction,
                "entry_price": entry_deal.price,
                "exit_price": exit_deal.price,
                "entry_time": entry_deal.time,
                "exit_time": exit_deal.time,
                "profit": total_profit,
                "volume": entry_deal.volume
            })
            
    closed_positions.sort(key=lambda x: x["exit_time"], reverse=True)
    return closed_positions[:limit]

def calculate_regime_forecast_accuracy(closed_positions: list[dict]) -> float:
    if not closed_positions:
        return 1.0
    
    matches = 0
    for pos in closed_positions:
        symbol = pos["symbol"]
        entry_time = pos["entry_time"]
        
        hmm_state, atr = get_entry_meta_from_db(symbol, entry_time)
        
        p_diff = pos["exit_price"] - pos["entry_price"]
        if pos["direction"] == 1: # SELL
            p_diff = -p_diff
            
        if atr > 0:
            r_multiple = p_diff / (atr * 4.0)
        else:
            r_multiple = 0.0
            
        if r_multiple >= 1.0:
            outcome_label = "BULL"
        elif r_multiple <= -1.0:
            outcome_label = "BEAR"
        else:
            outcome_label = "RANGE"
            
        # Clean hmm_state comparison
        clean_hmm = hmm_state.upper()
        clean_outcome = outcome_label.upper()
        if clean_hmm == clean_outcome or ("BULL" in clean_hmm and "BULL" in clean_outcome) or ("BEAR" in clean_hmm and "BEAR" in clean_outcome) or ("RANGE" in clean_hmm and "RANGE" in clean_outcome):
            matches += 1
            
    return matches / len(closed_positions)

def calculate_feature_stability_score(symbol: str) -> float:
    import glob
    import json
    try:
        diag_file = Path(f"C:/Sentinel_Project/shap_diagnostics/{symbol}_diag.json")
        if not diag_file.exists():
            return 1.0
        
        with open(diag_file, "r") as f:
            current_diag = json.load(f)
        current_weights = current_diag.get("weights", {})
        if not current_weights:
            return 1.0
        
        history_file = Path(f"C:/Sentinel_Project/shap_diagnostics/{symbol}_shap_history.json")
        history = []
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                pass
                
        history.append(current_weights)
        if len(history) > 50:
            history.pop(0)
            
        with open(history_file, "w") as f:
            json.dump(history, f)
            
        if len(history) < 5:
            return 1.0
            
        prev_history = history[:-1][-20:]
        avg_weights = {}
        for k in current_weights.keys():
            vals = [h.get(k, 0.0) for h in prev_history]
            avg_weights[k] = np.mean(vals) if vals else 0.0
            
        feature_keys = list(current_weights.keys())
        u = np.array([current_weights.get(k, 0.0) for k in feature_keys])
        v = np.array([avg_weights.get(k, 0.0) for k in feature_keys])
        
        dot = np.dot(u, v)
        norm_u = np.linalg.norm(u)
        norm_v = np.linalg.norm(v)
        
        if norm_u > 0 and norm_v > 0:
            similarity = dot / (norm_u * norm_v)
            return float(similarity)
    except Exception as e:
        logger.warning(f"[STABILITY_ERR] {symbol}: {e}")
    return 1.0

def run_composite_health_audit() -> float:
    # Evaluates the three-metric health dashboard globally/across symbols.
    # Returns size multiplier: 1.0 (0 fails), 0.67 (1 fail), 0.50 (2 fails), 0.0 (3 fails/freeze)
    closed_positions = get_trailing_closed_positions(50)
    
    # Metric 1: Trailing 50-trade Live PSR
    psr_fail = False
    if len(closed_positions) >= 25:
        returns = [_deal_to_return_dict(pos) for pos in closed_positions]
        returns = [r for r in returns if r is not None]
        if returns:
            psr_val = calculate_psr(returns)
            if psr_val < 0.80:
                psr_fail = True
                logger.warning(f"[HEALTH] Metric 1 (PSR) Failed: PSR={psr_val:.4f} < 0.80")
                
    # Metric 2: Regime Forecast Accuracy
    accuracy_fail = False
    if len(closed_positions) >= 5:
        accuracy = calculate_regime_forecast_accuracy(closed_positions)
        if accuracy < 0.40:
            accuracy_fail = True
            logger.warning(f"[HEALTH] Metric 2 (HMM Accuracy) Failed: Accuracy={accuracy:.2%} < 40.0%")
            
    # Metric 3: Feature Stability Score (check XAUUSD as default proxy symbol)
    stability_fail = False
    stability = calculate_feature_stability_score("XAUUSD")
    if stability < 0.80:
        stability_fail = True
        logger.warning(f"[HEALTH] Metric 3 (SHAP Stability) Failed: CosineSim={stability:.4f} < 0.80")
        
    # Count failures
    fails = sum([psr_fail, accuracy_fail, stability_fail])
    
    if fails == 0:
        mult = 1.0
    elif fails == 1:
        mult = 0.67
    elif fails == 2:
        mult = 0.50
    else:
        mult = 0.0 # Execution freeze
        logger.critical(f"[HEALTH] [EXECUTION_FREEZE] All 3 health metrics failed! Freezing execution.")
        
    # Trigger low profit pairs update
    update_low_profit_pairs_tracker(closed_positions)
        
    # Log current health status
    logger.info(f"[HEALTH_DASHBOARD] PSR Fail={psr_fail} | HMM Acc Fail={accuracy_fail} | SHAP Stability Fail={stability_fail} | Size Mult={mult}")
    return mult

class SentinelProfitManager:
    """
    Institution-Grade Sentinel Profit Manager v25.0
    ─────────────────────────────────────────────────────────────────────────
    All 14 identified bugs from v23.2 resolved. Key design changes:

      PositionState registry   — single source of truth, GC'd on close
      OracleCache              — one ArcticDB I/O per symbol per 5 s cycle
      ExitScoreEngine          — weighted multi-dimensional scoring
      ScaleOutCoordinator      — live volume, min_lot validation, no overlap
      Equity-inclusive DD      — Fortress now fires on actual open exposure
      R-multiple PSR           — lot-size-agnostic Sharpe distribution
      Fortress trail           — trails toward current price, not retrace below entry
      TP modification fixed    — target_tp always sent (not pos.tp)
      Execution dedup          — liquidation_sent flag prevents double-close
      Instrument-safe ATR      — 0.20% price floor, broker stop floor, H1 floor
      HMM NEUTRAL handled      — NEUTRAL/RANGING/CHOPPY states have no regime conflict
      State GC                 — closed position state removed every loop
      Velocity kill tightened  — 5-sample window, profit_r > 2.5R protection
      BE SL armored            — normalize_stop applied to all SL paths
    """

    def __init__(self):
        if not mt5.initialize():
            logger.critical("[FATAL] MT5 init failed.")
            sys.exit(1)
        try:
            from sentinel_config import WATCHLIST
            for sym in WATCHLIST:
                mt5.symbol_select(sym, True)
        except Exception:
            pass

        self._states: dict[int, PositionState] = {}
        self._oracle  = OracleCache(ttl=REGIME_POLL_INTERVAL)
        self.level_resolver   = StructuralLevelResolver(self._oracle)
        self.tp_engine        = TPPlacementEngine(self._oracle, self.level_resolver)
        self._tp_violation_log = []
        self.hermes_agent = None

        self._last_regime_check: dict[str, float] = {}
        logger.info("Profit Manager v25.0 online — Institution-Grade CADES ACTIVE.")

    # ── State Management ──────────────────────────────────────────────────────
    def _get_state(self, pos) -> PositionState:
        if pos.ticket not in self._states:
            oracle = self._oracle.get(pos.symbol)
            oracle_strat = oracle.get("strategy_type", "MOMENTUM") if oracle else "MOMENTUM"
            
            from gitagent_strategy_logger import StrategyExecutionLogger
            sl = StrategyExecutionLogger(str(pos.ticket))
            try:
                vol_ratio = 1.0
                ofi_vel = 0.0
                xgb_p = 0.5
                kronos_p = 0.5
                conviction = 0.8
                bocpd_prob = 0.2
                wasserstein_idx = 1
                
                if oracle:
                    vol_ratio = float(oracle.get("volatility_ratio", 1.0))
                    ofi_vel = float(oracle.get("ofi_velocity", 0.0))
                    row = oracle.get("raw_row")
                    if row is not None:
                        xgb_p = float(row.get("xgboost_prob", row.get("xgb_p", 0.5)))
                        kronos_p = float(row.get("kronos_prob", row.get("kronos_p", 0.5)))
                        conviction = float(row.get("meta_conviction", 0.8))
                        bocpd_prob = float(row.get("ofi_velocity", 0.2))
                        hmm_state_str = str(row.get("hmm_state", "RANGE")).upper()
                        if "TREND" in hmm_state_str:
                            wasserstein_idx = 0
                        elif "CRISIS" in hmm_state_str:
                            wasserstein_idx = 2
                        else:
                            wasserstein_idx = 1
                            
                sl.capture_entry_cognitive_state(
                    raw_probability_vector=[xgb_p, kronos_p],
                    adjusted_conviction=conviction,
                    activity_ratio=vol_ratio,
                    bocpd_prob=ofi_vel,
                    wasserstein_idx=wasserstein_idx,
                    volatility_ratio=vol_ratio,
                    ofi_velocity=ofi_vel
                )
            except Exception as logger_err:
                logger.error(f"[LOGGER_ERR] Failed to capture cognitive state for ticket {pos.ticket}: {logger_err}")
            
            self._states[pos.ticket] = PositionState(
                ticket=pos.ticket,
                symbol=pos.symbol,
                direction=pos.type,
                entry_price=pos.price_open,
                entry_time=pos.time,
                entry_conviction=_parse_entry_conviction(pos.comment),
                entry_tf=_parse_entry_tf(pos.comment),
                strategy_type=_parse_strategy_type(pos.comment, default=oracle_strat),
                peak_price=pos.price_open,
                initial_sl=pos.sl,
                telemetry_logger=sl
            )
        return self._states[pos.ticket]

    def _cleanup_closed_states(self, active_tickets: set[int]):
        """[ARCH FIX] Remove stale state for closed positions. Prevents ticket-reuse bugs."""
        stale = set(self._states.keys()) - active_tickets
        for ticket in stale:
            logger.debug(f"[STATE_GC] Removed state for closed ticket #{ticket}")
            state = self._states[ticket]
            if hasattr(state, 'telemetry_logger') and state.telemetry_logger:
                import subprocess
                json_path = state.telemetry_logger.output_file
                state.telemetry_logger.write_atomic_anatomy_report("TERMINAL_AMNESIA_SYNC", mt5.TRADE_RETCODE_DONE)
                try:
                    subprocess.Popen([sys.executable, "gitagent_anatomy_visualizer.py", json_path])
                except Exception as e:
                    logger.error(f"Failed to launch visualizer for {ticket}: {e}")
            del self._states[ticket]

    # ── PSR Audit ─────────────────────────────────────────────────────────────
    def audit_performance(self):
        now   = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=7), now)
        if not deals:
            return

        returns = []
        for d in deals:
            if d.magic not in (MAGIC_NUMBER, MAGIC_LEGACY, MAGIC_TOP5):    continue
            if d.entry != mt5.DEAL_ENTRY_OUT:                  continue
            if d.time < PSR_EPOCH:                             continue
            r = _deal_to_return(d)
            if r is not None:
                returns.append(r)

        if not returns:
            return

        psr_val = calculate_psr(returns)
        logger.info(f"[PSR_AUDIT] PSR={psr_val:.4f} n={len(returns)} threshold={PSR_THRESHOLD}")
        
        # v30.50-CADES Composite Health Matrix execution
        try:
            health_mult = run_composite_health_audit()
            
            # Read and write to dynamic_risk_params.json
            config = load_risk_config()
            config["health_size_multiplier"] = health_mult
            with open("dynamic_risk_params.json", "w", encoding="utf-8") as fh:
                json.dump(config, fh, indent=4)
                
            logger.info(f"[HEALTH] Saved health_size_multiplier={health_mult} to dynamic_risk_params.json")
            
            if health_mult == 0.0:
                logger.critical("[HEALTH] SRE Exec Freeze initiated due to 3 health metric failures.")
                self._sre_halt(psr_val)
        except Exception as health_err:
            logger.error(f"[HEALTH_ERR] Composite health audit failed: {health_err}")

        if psr_val < PSR_THRESHOLD:
            logger.critical(f"[PSR_DEGRADATION] PSR={psr_val:.4f} < {PSR_THRESHOLD}")
            self._sre_halt(psr_val)

    def _sre_halt(self, psr_val: float):
        payload = {
            "error_type": "PSR_DEGRADATION", "psr_value": round(psr_val, 6),
            "timestamp": int(time.time()), "status": "HALTED",
            "reason": f"Live PSR {psr_val:.4f} below {PSR_THRESHOLD}",
        }
        ticket_path = DIAG_DIR / f"psr_fail_{int(time.time())}.json"
        try:
            from filelock import FileLock
            with FileLock(str(ticket_path) + ".lock"):
                with open(ticket_path, "w") as fh:
                    json.dump(payload, fh, indent=2)
        except Exception as e:
            logger.error(f"[SRE_HALT_WRITE_ERR] {e}")
        notify(f"**PSR_DEGRADATION**\nPSR={psr_val:.4f} < {PSR_THRESHOLD}\nSRE halt triggered.")

    # ── Profit Locking: SL/TP Modification ───────────────────────────────────
    def _apply_profit_locks(
        self, pos, ps: PositionState, macro_atr: float,
        sl_mult: float, tp_mult: float, current_price: float, drawdown: float
    ):
        """
        v25.0 profit locking engine with v28.33 Strict Green Guard & 80% Trail Lock.
        """
        info = mt5.symbol_info(pos.symbol)
        if not info:
            return
        digits  = info.digits
        is_buy  = ps.is_buy()
        entry   = ps.entry_price
        delta   = ps.profit_delta(current_price)
        tick    = mt5.symbol_info_tick(pos.symbol)
        curr    = (tick.bid if is_buy else tick.ask) if tick else current_price

        # For MEAN_REVERSION trades (Meridian), apply the specific meridian exit rules
        if ps.strategy_type == "MEAN_REVERSION":
            rates = mt5.copy_rates_from_pos(pos.symbol, mt5.TIMEFRAME_M15, 0, 50)
            if rates is not None and len(rates) >= 20:
                closes = np.array([r['close'] for r in rates])
                
                # BB Mid (SMA 20)
                bb_mid = float(np.mean(closes[-20:]))
                bb_std = float(np.std(closes[-20:]))
                
                # KC Mid (EMA 20)
                alpha = 2.0 / (20.0 + 1.0)
                kc_mid = closes[-20]
                for p in closes[-19:]:
                    kc_mid = p * alpha + kc_mid * (1 - alpha)
                
                # ATR 20
                tr_list = []
                for i in range(len(rates) - 20, len(rates)):
                    prev_close = rates[i-1]['close']
                    tr = max(rates[i]['high'] - rates[i]['low'],
                             abs(rates[i]['high'] - prev_close),
                             abs(rates[i]['low'] - prev_close))
                    tr_list.append(tr)
                kc_atr = float(np.mean(tr_list))
                kc_upper = float(kc_mid + 2.0 * kc_atr)
                kc_lower = float(kc_mid - 2.0 * kc_atr)
                
                # Check exit conditions
                should_exit = False
                exit_reason = ""
                if is_buy:
                    if curr >= bb_mid:
                        should_exit = True
                        exit_reason = "Meridian Target hit: Price >= BB Mid"
                    elif curr >= kc_upper:
                        should_exit = True
                        exit_reason = "Meridian Target hit: Price >= KC Upper"
                else:
                    if curr <= bb_mid:
                        should_exit = True
                        exit_reason = "Meridian Target hit: Price <= BB Mid"
                    elif curr <= kc_lower:
                        should_exit = True
                        exit_reason = "Meridian Target hit: Price <= KC Lower"
                        
                if should_exit:
                    logger.info(f"[MERIDIAN_EXIT] {pos.symbol} #{pos.ticket} exiting: {exit_reason} (Price={curr:.5f}, BB_Mid={bb_mid:.5f}, KC_Upper/Lower={kc_upper if is_buy else kc_lower:.5f})")
                    market_close(pos, reason=exit_reason)
                    return
            return  # Skip Momentum profit locks/Fortress Trail for Mean-Reversion trades

        # ── Strict Green Guard Check (v28.33) ────────────────────────────────
        is_in_profit = (pos.type == mt5.ORDER_TYPE_BUY and curr > pos.price_open) or \
                       (pos.type == mt5.ORDER_TYPE_SELL and curr < pos.price_open)
        if not is_in_profit:
            return  # STRICT GREEN GUARD: Never calculate or move trails while in the red.

        # Start from current physical levels
        target_sl = pos.sl
        modify_sl = False

        # ── Trailing Stop Milestone & Activation Gate (v28.33 Constitution) ──
        initial_sl = getattr(ps, "initial_sl", 0.0)
        if initial_sl == 0.0:
            if pos.sl != 0.0:
                ps.initial_sl = pos.sl
                initial_sl = pos.sl
            else:
                raw_initial = ps.entry_price - (sl_mult * macro_atr) if is_buy else ps.entry_price + (sl_mult * macro_atr)
                initial_sl = normalize_stop(pos.symbol, curr, raw_initial, is_sl=True, is_buy=is_buy)
                initial_sl = round(initial_sl, digits)
                ps.initial_sl = initial_sl

        # Calculate SL Distance
        sl_dist = abs(entry - initial_sl)
        if sl_dist <= 0.0:
            sl_dist = sl_mult * macro_atr
        if sl_dist <= 0.0:
            sl_dist = 1.0

        # Mandate Symmetric Take Profits: structurally lock TP distance to min 1.5x SL distance
        min_tp_dist = 1.5 * sl_dist
        tp_dist = max(tp_mult * macro_atr, min_tp_dist)
        
        # Determine active regime for D_guard (v30.60 RANGE Logic)
        active_regime_for_guard = "TRENDING"
        try:
            from arcticdb import Arctic
            store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
            row = store["oracle_cache"].read(f"{pos.symbol}_meta").data.iloc[-1]
            active_regime_for_guard = str(row["wasserstein_state"]).upper()
        except:
            pass
            
        # Crypto Triple-Barrier Protocol: Regime-Aware TP Squashing
        crypto_keywords = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOT", "LINK", "AVAX", "LTC", "BCH", "TRX", "DOGE"}
        is_crypto = any(k in pos.symbol.upper() for k in crypto_keywords)
        
        if is_crypto and "RANGE" in active_regime_for_guard:
            tp_dist *= 0.15 # Squash Take Profit distance by 0.15x

        # Always recompute TP dynamically
        new_tp = (entry + tp_dist) if is_buy else (entry - tp_dist)
        target_tp  = normalize_stop(pos.symbol, curr, new_tp, is_sl=False, is_buy=is_buy)
        target_tp  = round(target_tp, digits)
        modify_tp  = (pos.tp == 0.0 or abs(pos.tp - target_tp) > 1e-5)

        # Calculate Target Path
        d_target = abs(target_tp - entry)
        
        if "RANGE" in active_regime_for_guard:
            d_guard = 0.50 * d_target
        else:
            d_guard = 0.80 * d_target

        d_current = abs(curr - entry)

        trail_allowed = (d_current >= d_guard)
        
        # Crypto Regime-Aware TP Squashing Scale Out
        if is_crypto and "RANGE" in active_regime_for_guard:
            if d_current >= 1.75 * macro_atr and not getattr(ps, "crypto_squash_done", False):
                logger.info(f"[CRYPTO_SQUASH] {pos.symbol} breached +1.75 ATR in RANGE. Liquidating 75%.")
                tick = mt5.symbol_info_tick(pos.symbol)
                info = mt5.symbol_info(pos.symbol)
                if safe_scale_out(pos, ps, 0.75, "CRYPTO_RANGE_HARVEST", info, tick):
                    ps.crypto_squash_done = True
            
            # Disable parabolic trailing
            trail_allowed = False
        
        # Scenario A: Terminal RANGE Harvest (Non-Crypto)
        elif "RANGE" in active_regime_for_guard and d_current >= d_guard and not ps.zone1_done:
            logger.info(f"[RANGE_HARVEST] {pos.symbol} breached D_guard {d_guard:.5f} in RANGE. Harvesting 75%.")
            tick = mt5.symbol_info_tick(pos.symbol)
            info = mt5.symbol_info(pos.symbol)
            if safe_scale_out(pos, ps, 0.75, "RANGE_TERMINAL_HARVEST", info, tick):
                ps.zone1_done = True


        # Unconditional Stop Freeze
        if not trail_allowed:
            # Stop loss must remain frozen at initial_sl
            target_sl = initial_sl
            modify_sl = (pos.sl == 0.0 or abs(pos.sl - initial_sl) > 1e-5)
        else:
            # Trailing is allowed after 80% target is reached
            # Let's trail SL at 1.5 * macro_atr behind current price to protect profits
            trail_sl = (curr - 1.5 * macro_atr) if is_buy else (curr + 1.5 * macro_atr)
            
            # Tighter trail at 85% TP Killshot (0.5 * macro_atr behind current price)
            if d_current >= 0.85 * d_target:
                trail_sl = (curr - 0.5 * macro_atr) if is_buy else (curr + 0.5 * macro_atr)
                
            # Move only in the direction that protects the trade (advance_sl logic)
            candidate = normalize_stop(pos.symbol, curr, trail_sl, is_sl=True, is_buy=is_buy)
            candidate = round(candidate, digits)
            if is_buy and (target_sl == 0.0 or candidate > target_sl):
                target_sl = candidate
                modify_sl = True
            elif not is_buy and (target_sl == 0.0 or candidate < target_sl):
                target_sl = candidate
                modify_sl = True

        # ── Dispatch modification ────────────────────────────────────────────
        if modify_sl or modify_tp:
            mod_req = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "symbol":   pos.symbol,
                "position": pos.ticket,
                "sl":       float(target_sl),
                "tp":       float(target_tp),
            }
            res = mt5.order_send(mod_req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(
                    f"[PROFIT_LOCK] {pos.symbol} #{pos.ticket}: "
                    f"SL={target_sl:.5f} TP={target_tp:.5f} | "
                    f"R={ps.profit_r(current_price, macro_atr, sl_mult):.2f}"
                )
            else:
                code = res.retcode if res else "N/A"
                msg  = res.comment if res else ""
                logger.warning(
                    f"[PROFIT_LOCK_FAIL] {pos.symbol} #{pos.ticket}: {code} {msg}"
                )

    # ── Event Horizon Protection ──────────────────────────────────────────────
    def _event_horizon_protection(self, pos, ps):
        """PURGED: Event horizon scale-outs violate structural Swing metrics."""
        pass

    # ── Naked Sweep (orphaned positions) ──────────────────────────────────────
    def _naked_sweep(self, pos):
        """
        v25.0: Instrument-aware ATR floor.
        BUG FIX: raw_atr=0.0010 was a forex constant — useless for BTCUSD.
        """
        tick = mt5.symbol_info_tick(pos.symbol)
        info = mt5.symbol_info(pos.symbol)
        if not tick or not info:
            return

        # Instrument-safe ATR
        macro_atr = get_safe_atr(pos.symbol, 0.0, pos.price_open)
        is_buy    = (pos.type == mt5.ORDER_TYPE_BUY)
        curr      = tick.bid if is_buy else tick.ask

        # Fetch HMM state and multipliers
        oracle = self._oracle.get(pos.symbol)
        hmm_state = oracle.get("hmm_state", "NEUTRAL") if oracle else "NEUTRAL"
        
        # 1. Server-Side Hard Anchor Minimums
        raw_sl = calculate_institutional_hard_stop(pos.price_open, is_buy, macro_atr, hmm_state)
        sl_dist = abs(pos.price_open - raw_sl)
        
        tp_mult = get_atr_multipliers(pos.symbol, hmm_state)[1]
        min_tp_dist = 1.5 * sl_dist
        tp_dist = max(tp_mult * macro_atr, min_tp_dist)
        
        raw_tp = (pos.price_open + tp_dist) if is_buy else (pos.price_open - tp_dist)
        
        # Only inject if missing
        final_sl = normalize_stop(pos.symbol, curr, raw_sl if pos.sl == 0.0 else pos.sl, is_sl=True,  is_buy=is_buy)
        final_tp = normalize_stop(pos.symbol, curr, raw_tp if pos.tp == 0.0 else pos.tp, is_sl=False, is_buy=is_buy)

        if pos.sl == 0.0 or pos.tp == 0.0:
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP, "symbol": pos.symbol,
                "position": pos.ticket, "sl": final_sl, "tp": final_tp,
            })
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                msg = f"SL={final_sl:.5f} TP={final_tp:.5f}"
                logger.info(f"[NAKED_RESCUE] #{pos.ticket} {pos.symbol}: {msg}")
                TelemetryState.log_audit("PROFIT_MANAGER", pos.symbol, f"Naked Sweep Attached: {msg}")
            else:
                code = res.retcode if res else "N/A"
                logger.warning(f"[NAKED_FAIL] #{pos.ticket} {pos.symbol}: {code}")
                TelemetryState.log_audit("PROFIT_MANAGER", pos.symbol, f"Naked Sweep Failed: {code}")

    # ── Main Position Audit ───────────────────────────────────────────────────
    def _audit_positions(self, positions: list, config: dict):

        now               = time.time()
        drawdown, _equity = get_equity_drawdown()

        for pos in positions:
            symbol = pos.symbol
            ps     = self._get_state(pos)

            # Rate-limit oracle reads per symbol
            last_check = self._last_regime_check.get(symbol, 0.0)
            if now - last_check < REGIME_POLL_INTERVAL:
                continue
            self._last_regime_check[symbol] = now

            # Deduplication: skip if liquidation already confirmed within cooldown
            if ps.liquidation_sent and (now - ps.last_liquidation_ts) < LIQUIDATION_COOLDOWN_S:
                continue

            # Oracle read (cached — single ArcticDB I/O per symbol per cycle)
            oracle = self._oracle.get(symbol)
            if oracle is None:
                logger.debug(f"[ORACLE_SKIP] {symbol}: no oracle data available")
                continue

            hmm_state        = oracle.get("hmm_state", "NEUTRAL")
            sl_mult, tp_mult = get_atr_multipliers(symbol, hmm_state)

            if hasattr(ps, 'telemetry_logger') and ps.telemetry_logger:
                ps.telemetry_logger.capture_runtime_telemetry(
                    bar_step=int(now - ps.entry_time) // 60,
                    current_pnl=pos.profit,
                    condition_number=float(oracle.get("matrix_condition", 0.0)),
                    shaps={},
                    price=pos.price_current,
                    sl=pos.sl,
                    tp=pos.tp,
                    hmm_state=hmm_state,
                    conviction=ps.current_conviction
                )

            # Live price
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue
            current_price = tick.bid if pos.type == 0 else tick.ask
            broker_now    = tick.time if tick.time else int(now)

            # Instrument-safe ATR
            macro_atr = get_safe_atr(symbol, oracle.get("atr", 0.0), pos.price_open)
            if ps.entry_atr <= 0:
                ps.entry_atr = macro_atr

            # Conviction (TF-matched, from cached oracle — single read)
            live_p   = get_conviction_for_tf(oracle, ps.entry_tf)
            thesis_p = live_p if ps.is_buy() else (1.0 - live_p)

    

            if ps.is_buy():
                ps.peak_price = max(ps.peak_price, current_price)
            else:
                ps.peak_price = min(ps.peak_price if ps.peak_price > 0 else current_price, current_price)

            profit_r_now    = ps.profit_r(current_price, macro_atr, sl_mult)
            ps.peak_profit_r = max(ps.peak_profit_r, profit_r_now)

            # ENFORCED POSITION LIFE-CYCLE INVARIANT SCHEMA
            
            # 1. Read static broker side conditions natively
            hard_stop_loss = pos.sl
            hard_take_profit = pos.tp
            
            # 2. Hard Invariant Assertions: Structural check against explicit execution parameters
            if ps.is_buy():
                if current_price <= hard_stop_loss and hard_stop_loss > 0:
                    logger.warning(f"[MACRO_EXIT] {symbol} #{pos.ticket}: PHYSICAL_STOP_LOSS_BROKEN")
                    push_exit_signal(pos, "PHYSICAL_STOP_LOSS_BROKEN")
                    market_close(pos, "PHYSICAL_STOP_LOSS_BROKEN")
                    continue
                if current_price >= hard_take_profit and hard_take_profit > 0:
                    logger.warning(f"[MACRO_EXIT] {symbol} #{pos.ticket}: PHYSICAL_TAKE_PROFIT_HIT")
                    push_exit_signal(pos, "PHYSICAL_TAKE_PROFIT_HIT")
                    market_close(pos, "PHYSICAL_TAKE_PROFIT_HIT")
                    continue
            else:
                if current_price >= hard_stop_loss and hard_stop_loss > 0:
                    logger.warning(f"[MACRO_EXIT] {symbol} #{pos.ticket}: PHYSICAL_STOP_LOSS_BROKEN")
                    push_exit_signal(pos, "PHYSICAL_STOP_LOSS_BROKEN")
                    market_close(pos, "PHYSICAL_STOP_LOSS_BROKEN")
                    continue
                if current_price <= hard_take_profit and hard_take_profit > 0:
                    logger.warning(f"[MACRO_EXIT] {symbol} #{pos.ticket}: PHYSICAL_TAKE_PROFIT_HIT")
                    push_exit_signal(pos, "PHYSICAL_TAKE_PROFIT_HIT")
                    market_close(pos, "PHYSICAL_TAKE_PROFIT_HIT")
                    continue
            
            # 3. Macro Oracle Check: Evaluated formally by the HMM Regime state
            if hmm_state == "STRUCTURAL_REGIME_INVERSION":
                logger.warning(f"[MACRO_EXIT] {symbol} #{pos.ticket}: ORACLE_REGIME_INVERSION_VERIFIED")
                push_exit_signal(pos, "ORACLE_REGIME_INVERSION_VERIFIED")
                market_close(pos, "ORACLE_REGIME_INVERSION_VERIFIED")
                continue
                
            # 4. Total Trailing/Velocity Blindness: 
            # No other conditional paths are permitted. Position holds steady.
            logger.debug(f"[OK] {symbol} #{pos.ticket}: HOLDING STRUCTURAL TRAJECTORY | HMM={hmm_state}")

    # ── Monitor Loop ──────────────────────────────────────────────────────────
    def monitor_loop(self):
        logger.info("Monitor loop started — PSR audit every 10 min | scan every 1 s.")
        last_audit = 0.0

        while True:
            try:
                if time.time() - last_audit > 600:
                    self.audit_performance()
                    last_audit = time.time()

                scan_interval = 10
                closed_deals = get_trailing_closed_positions(limit=50)
                if closed_deals:
                    one_hour_ago = time.time() - 3600
                    recent_closed = [c for c in closed_deals if c.get("exit_time", 0) > one_hour_ago]
                    if recent_closed:
                        wins = sum(1 for c in recent_closed if c.get("profit", 0) > 0)
                        win_rate = wins / len(recent_closed)
                        if win_rate < 0.25:
                            logger.info(f"[THROTTLING] Win rate {win_rate:.0%} < 25% over last hour. Throttling scan to 30s.")
                            scan_interval = 30

                sentinel_pos  = mt5.positions_get(magic=MAGIC_NUMBER)  or []
                legacy_pos    = mt5.positions_get(magic=MAGIC_LEGACY)  or []
                top5_pos      = mt5.positions_get(magic=MAGIC_TOP5)    or []
                all_positions = list(sentinel_pos) + list(legacy_pos) + list(top5_pos)
                
                # Naked Kill Switch disabled: We want physical stops.
                
                active_tickets = {p.ticket for p in all_positions}

                # State cleanup [ARCH FIX] — prevents ticket reuse state corruption
                self._cleanup_closed_states(active_tickets)

                config = load_risk_config()

                active_audit_positions = []
                for pos in all_positions:
                    ps = self._get_state(pos)
                    
                    # Naked sweep strictly attaches missing SL/TP, no retroactive widening
                    if pos.tp == 0.0 or pos.sl == 0.0:
                        self._naked_sweep(pos)
                    
                    active_audit_positions.append(pos)

                if active_audit_positions:
                    self._audit_positions(active_audit_positions, config)

                time.sleep(scan_interval)

            except Exception as e:
                import traceback
                logger.error(f"Monitor loop error: {e}\n{traceback.format_exc()}")
                time.sleep(10)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock.bind(("127.0.0.1", 65436))
    except socket.error:
        print("[FATAL] Profit Manager already running.")
        sys.exit(1)

    mgr = SentinelProfitManager()
    try:
        mgr.monitor_loop()
    except KeyboardInterrupt:
        mt5.shutdown()

    def _reconcile_tp_compliance(self) -> None:
        import logging
        from datetime import datetime, timezone
        log = logging.getLogger("CADES.ProfitManager.ZetaReconcile")
        now = datetime.now(tz=timezone.utc)

        for ticket, state in list(self._states.items()):
            symbol    = state.symbol
            entry     = state.entry_price
            sl        = state.initial_sl
            tp        = state.peak_price # placeholder, we don't store actual TP in PositionState, we can get it from MT5 position. 
            direction = 0 if state.direction == mt5.ORDER_TYPE_BUY else 1

            pos_info = mt5.position_get(ticket=ticket)
            if pos_info:
                current_tp = pos_info[0].tp
                sl = pos_info[0].sl
            else:
                continue

            audit = self.tp_engine.audit_open_position(
                symbol=symbol, entry=entry, sl=sl, current_tp=current_tp, direction=direction
            )

            if not audit.is_valid and getattr(state, "zeta_status", "") != "LEGACY_VIOLATION":
                log.warning(f"[ZetaReconcile] #{ticket} {symbol} is a LEGACY_VIOLATION: {audit.rejection_reason}")
                state.zeta_status = "LEGACY_VIOLATION"
                self._tp_violation_log.append({
                    "ticket":    ticket,
                    "symbol":    symbol,
                    "reason":    audit.rejection_reason,
                    "tp":        current_tp,
                    "tp_pct":    audit.tp_distance_pct,
                    "detected":  now.isoformat(),
                })

            # 2. Time-stop enforcement (Article III)
            max_days = getattr(state, "time_stop_days", None)
            if max_days and getattr(state, "entry_time", None):
                elapsed_trading_days = self._count_trading_days(datetime.fromtimestamp(state.entry_time, timezone.utc), now)

                hmm_state = self._oracle.get(symbol).get("hmm_state", "RANGE") if self._oracle.get(symbol) else "RANGE"
                wass_dist = 0.20 # Default

                in_strong_trend = (hmm_state == "TRENDING" and wass_dist is not None and wass_dist < 0.15)
                if not in_strong_trend and elapsed_trading_days >= max_days:
                    log.warning(f"[ZetaTimeStop] #{ticket} {symbol} exceeded time-stop of {max_days} days. Queuing market exit.")
                    state.zeta_status = "TIME_STOP_TRIGGERED"
                    self._queue_time_stop_exit(ticket, symbol, state)

    @staticmethod
    def _count_trading_days(start, end) -> int:
        import numpy as np
        days = np.busday_count(start.date(), end.date(), weekmask="Mon Tue Wed Thu Fri")
        return int(days)

    def _modify_tp_on_broker(self, ticket: int, new_tp: float) -> bool:
        try:
            pos = mt5.position_get(ticket=ticket)
            if not pos: return False
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": pos[0].symbol,
                "sl": pos[0].sl,
                "tp": new_tp
            }
            res = mt5.order_send(request)
            return res.retcode == mt5.TRADE_RETCODE_DONE
        except Exception as exc:
            import logging
            logging.getLogger("CADES.ProfitManager").error(f"[BrokerModify] TP mod failed for #{ticket}: {exc}")
            return False

    def _queue_time_stop_exit(self, ticket: int, symbol: str, state) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").warning(f"[TimeStop] Executing market exit for #{ticket} {symbol}")
        market_close(mt5.position_get(ticket=ticket)[0], reason="ZETA_TIME_STOP")

    def _emit_tp_gate_reject(self, ticket: int, symbol: str, result: TPValidationResult) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").error(f"[TP_GATE_REJECT] #{ticket} {symbol}: {result.rejection_reason} | proposed_tp={result.proposed_tp:.5f} rr={result.rr_ratio:.2f}")

    def _emit_tp_adjustment_failure(self, ticket: int, symbol: str, adjusted_tp: float) -> None:
        import logging
        logging.getLogger("CADES.ProfitManager").error(f"[ZetaAdjustFail] Broker TP modification failed for #{ticket} {symbol} -> {adjusted_tp:.5f}.")

    def _apply_time_stop_dampening(self, base_score: float, elapsed_trading_days: int, max_days: int, in_strong_trend: bool) -> float:
        if in_strong_trend or max_days is None: return base_score
        time_consumed = elapsed_trading_days / max_days
        if time_consumed < 0.70: return base_score
        dampening_factor = 1.0 - 0.5 * ((time_consumed - 0.70) / 0.30)
        return base_score * max(0.5, dampening_factor)

    def run_legacy_violation_audit(self) -> dict:
        import logging
        logger = logging.getLogger("CADES.ProfitManager.LegacyAudit")
        logger.info("[LegacyAudit] Starting DIRECTIVE ZETA startup audit...")
        summary = {"total_positions": 0, "violations": [], "compliant": [], "warnings": []}
        for ticket, state in self._states.items():
            summary["total_positions"] += 1
            pos_info = mt5.position_get(ticket=ticket)
            if not pos_info: continue
            audit = self.tp_engine.audit_open_position(
                symbol=state.symbol, entry=state.entry_price, sl=pos_info[0].sl, current_tp=pos_info[0].tp, direction=0 if state.direction == mt5.ORDER_TYPE_BUY else 1
            )
            if not audit.is_valid:
                state.zeta_status = "LEGACY_VIOLATION"
                summary["violations"].append({"ticket": ticket, "symbol": state.symbol, "reason": audit.rejection_reason})
            else:
                state.zeta_status = "COMPLIANT"
                summary["compliant"].append(ticket)
        logger.info(f"[LegacyAudit] Complete: {len(summary['violations'])} violations, {len(summary['compliant'])} compliant.")
        return summary
