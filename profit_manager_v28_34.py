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
import io, json, logging, os, re, socket, sys, time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from dotenv import load_dotenv
from scipy import stats

from agents.risk_agent import check_upcoming_tier1_events

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────────
MAGIC_NUMBER            = 142
MAGIC_LEGACY            = 17300
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
    conviction_history:   list = field(default_factory=list)
    thesis_decay_streak:  int  = 0

    # Regime gate
    regime_conflict_count: int = 0

    # Conviction tracking
    last_conviction_update: float = 0.0
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
def calculate_atr_h1(symbol: str, period: int = 14) -> float:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 1, period + 1)
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
    v25.0 instrument-safe ATR.
    BUG FIX: raw_atr=0.0010 was a hardcoded forex value — useless for BTCUSD/indices.
    Three floors: H1 computed, 0.20% of price, broker stop level.
    """
    h1_atr      = calculate_atr_h1(symbol)
    price_floor = pos_open * 0.002          # 0.20% of open price
    info        = mt5.symbol_info(symbol)
    broker_floor = (info.trade_stops_level * info.point * 3) if info else 0.0
    candidates  = [v for v in [h1_atr, oracle_atr, price_floor, broker_floor] if v > 0]
    return max(candidates) if candidates else 1e-5


# ══════════════════════════════════════════════════════════════════════════════
#  EQUITY-INCLUSIVE DRAWDOWN  [CRITICAL FIX] was closed-deals only
# ══════════════════════════════════════════════════════════════════════════════
def get_equity_drawdown() -> tuple[float, float]:
    """
    v25.0: Uses account.equity which includes all open unrealized P&L.
    BUG FIX: Previous version used history_deals_get (closed only) →
             10 positions each −2.9% open reported 0% drawdown.
    Returns (drawdown_fraction, current_equity).
    """
    acc = mt5.account_info()
    if not acc:
        return 0.0, 0.0
    try:
        now_utc     = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        deals       = mt5.history_deals_get(today_start, now_utc)
        realized_today = sum(
            d.profit for d in (deals or []) if d.entry == mt5.DEAL_ENTRY_OUT
        )
        # Approximate start-of-day equity (closed P&L removed, unrealized at start = 0)
        start_equity = acc.balance - realized_today
        peak         = max(start_equity if start_equity > 0 else acc.balance, acc.equity)
        drawdown     = (peak - acc.equity) / peak if peak > 0 else 0.0
        return max(0.0, drawdown), float(acc.equity)
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

    # ── 1. Virtual Stop Loss / Take Profit (HARD EXIT) ───────────────────────
    sl_level = (ps.entry_price - sl_mult * macro_atr) if is_buy else (ps.entry_price + sl_mult * macro_atr)
    tp_level = (ps.entry_price + sl_mult * 2.0 * macro_atr) if is_buy else (ps.entry_price - sl_mult * 2.0 * macro_atr)

    if (is_buy and current_price <= sl_level) or (not is_buy and current_price >= sl_level):
        sig.hard_exit = True
        sig.reason_primary = "[HARD VIRTUAL SL]"
        sig.reasons.append(f"Price={current_price:.5f} ≤ VSL={sl_level:.5f}")
        return sig

    if (is_buy and current_price >= tp_level) or (not is_buy and current_price <= tp_level):
        sig.hard_exit = True
        sig.reason_primary = "[VIRTUAL TP]"
        sig.reasons.append(f"Price={current_price:.5f} ≥ VTP={tp_level:.5f}")
        return sig

    # ── 2. Macro Shock / Sentiment Kill (HARD EXIT) ──────────────────────────
    if (pos_dir == "BUY" and sentiment < -0.65) or (pos_dir == "SELL" and sentiment > 0.65):
        sig.hard_exit = True
        sig.reason_primary = "[MACRO SHOCK]"
        sig.reasons.append(f"Sentiment={sentiment:.2f} threshold breached for {pos_dir}")
        return sig

    # ── 3. Velocity Kill (HARD EXIT with profit gate) ────────────────────────
    # BUG FIX: v23.2 used 3-tick window (too noisy) and had no profit protection.
    # v25.0: 5-sample minimum, velocity kill suppressed if profit_r > 2.5R.
    hist = ps.conviction_history
    if len(hist) >= 5:
        vel_limit = -0.20 if symbol.upper() in _JPY_PAIRS else -0.30
        delta_p   = hist[-1] - hist[-5]
        if delta_p < vel_limit:
            if profit_r > 2.5:
                logger.info(
                    f"[VEL_GUARD] {symbol} #{ps.ticket}: velocity suppressed — profit_r={profit_r:.2f}R > 2.5R"
                )
            else:
                sig.hard_exit = True
                sig.reason_primary = "[VELOCITY KILL]"
                sig.reasons.append(f"dP/dt={delta_p:.3f} < {vel_limit} over 5 ticks | R={profit_r:.2f}")
                return sig

    # ── From here: soft scored exits ─────────────────────────────────────────

    # ── 4. Regime Conflict (scored) ──────────────────────────────────────────
    # BUG FIX: v23.2 had no profit gate. v25.0 scales required persistence with R.
    is_conflict = (pos_dir == "BUY" and hmm == "BEAR") or (pos_dir == "SELL" and hmm == "BULL")
    if is_conflict:
        ps.regime_conflict_count += 1
        # Higher profit → require more persistent regime conflict before exiting
        r_gate      = max(3, int(3 + max(0, profit_r)))   # 0R→3, 3R→6, 5R→8 confirms
        persistence = min(ps.regime_conflict_count / r_gate, 1.0)
        sig.score  += 0.40 * persistence
        sig.reasons.append(
            f"REGIME({hmm} vs {pos_dir}, count={ps.regime_conflict_count}/{r_gate})"
        )
    else:
        ps.regime_conflict_count = 0

    # ── 5. Thesis Decay (scored) ─────────────────────────────────────────────
    decay_rules     = get_decay_rules(symbol, config)
    min_hold_secs   = decay_rules.get("min_hold_hours", 12) * 3600
    decay_threshold = decay_rules.get("decay_threshold", 0.45)
    thesis_p        = live_p if is_buy else (1.0 - live_p)

    if elapsed >= min_hold_secs:
        entry_c        = abs(ps.entry_conviction - 0.5) + 0.5
        live_c         = abs(live_p - 0.5) + 0.5
        conviction_drop = entry_c - live_c

        if thesis_p < decay_threshold:
            ps.thesis_decay_streak += 1
        else:
            ps.thesis_decay_streak = 0

        streak_score   = min(ps.thesis_decay_streak / 3, 1.0)
        drop_score     = min(conviction_drop / 0.15, 1.0) if conviction_drop > 0.10 else 0.0
        decay_combined = max(streak_score, drop_score)

        if decay_combined > 0:
            sig.score  += 0.35 * decay_combined
            sig.reasons.append(
                f"DECAY(P={thesis_p:.2f}, streak={ps.thesis_decay_streak}, drop={conviction_drop:.3f})"
            )

    # ── 6. Dead Money (scored) ────────────────────────────────────────────────
    if h1_candles > 72 and abs(profit_r) < 0.25 and not is_weekend_pause:
        sig.score += 0.30
        sig.reasons.append(f"DEAD_MONEY(H1={h1_candles}bars, R={profit_r:.2f})")

    # ── 7. Theta Decay / Time Stop (scored) ──────────────────────────────────
    if elapsed > MAX_HOLDING_DAYS * 86400 and profit_r <= 0.0:
        sig.score += 0.50
        sig.reasons.append(f"THETA(held={elapsed/3600:.1f}h, R={profit_r:.2f})")

    # ── 8. Event Horizon suppression gate ────────────────────────────────────
    if sig.score > 0:
        try:
            has_event, event_desc = check_upcoming_tier1_events(symbol, threshold_hours=12.0)
            if has_event:
                logger.info(f"[EVENT_HORIZON_GATE] {symbol}: suppressing cognitive exits — {event_desc}")
                sig.score   = 0.0
                sig.reasons = [f"SUPPRESSED_PRE_EVENT({event_desc})"]
        except Exception as e:
            logger.warning(f"[EVENT_CHECK_ERR] {symbol}: {e}")

    # ── 9. Profit-weighted dampening ─────────────────────────────────────────
    # Positions in strong profit need a higher signal score to justify an exit.
    # A +4R position running with modest decay needs the system to fight for it.
    if profit_r > 2.0 and sig.score > 0:
        dampener  = max(0.30, 1.0 - (profit_r - 2.0) * 0.08)
        sig.score *= dampener

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
        if d.magic in (MAGIC_NUMBER, MAGIC_LEGACY):
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
            if d.magic not in (MAGIC_NUMBER, MAGIC_LEGACY):    continue
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

        # Always recompute TP dynamically
        new_tp = (entry + tp_dist) if is_buy else (entry - tp_dist)
        target_tp  = normalize_stop(pos.symbol, curr, new_tp, is_sl=False, is_buy=is_buy)
        target_tp  = round(target_tp, digits)
        modify_tp  = (pos.tp == 0.0 or abs(pos.tp - target_tp) > 1e-5)

        # Calculate Target Path
        d_target = abs(target_tp - entry)
        
        # Determine active regime for D_guard (v30.60 RANGE Logic)
        active_regime_for_guard = "TRENDING"
        try:
            from arcticdb import Arctic
            store = Arctic("lmdb://C:/Sentinel_Project/data/arctic_cache")
            row = store["oracle_cache"].read(f"{pos.symbol}_meta").data.iloc[-1]
            active_regime_for_guard = str(row["wasserstein_state"]).upper()
        except:
            pass
        
        if "RANGE" in active_regime_for_guard:
            d_guard = 0.50 * d_target
        else:
            d_guard = 0.80 * d_target

        d_current = abs(curr - entry)

        trail_allowed = (d_current >= d_guard)
        
        # Scenario A: Terminal RANGE Harvest
        if "RANGE" in active_regime_for_guard and d_current >= d_guard and not ps.zone1_done:
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
    def _event_horizon_protection(self, pos, ps: PositionState):
        if ps.event_horizon_done:
            return
        try:
            has_event, event_desc = check_upcoming_tier1_events(pos.symbol, threshold_hours=12.0)
        except Exception:
            return
        if not has_event:
            return

        logger.warning(f"[EVENT_HORIZON] {pos.symbol}: {event_desc} — 50% scale + BE SL")
        tick = mt5.symbol_info_tick(pos.symbol)
        info = mt5.symbol_info(pos.symbol)
        if not tick or not info:
            return

        if safe_scale_out(pos, ps, 0.50, "EVENT_HORIZON_50PCT", info, tick):
            ps.event_horizon_done = True

        is_buy  = ps.is_buy()
        curr    = tick.bid if is_buy else tick.ask
        offset  = info.trade_stops_level * info.point + info.spread * info.point
        be_sl   = (ps.entry_price + offset) if is_buy else (ps.entry_price - offset)
        be_sl   = normalize_stop(pos.symbol, curr, be_sl, is_sl=True, is_buy=is_buy)

        should_move = (is_buy  and (pos.sl == 0.0 or be_sl > pos.sl)) or \
                      (not is_buy and (pos.sl == 0.0 or be_sl < pos.sl))
        if should_move:
            mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP, "symbol": pos.symbol,
                "position": pos.ticket, "sl": be_sl, "tp": pos.tp,
            })

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
        time_held = tick.time - pos.time

        if time_held > 10:
            logger.critical(
                f"[KILL] Orphaned #{pos.ticket} ({pos.symbol}) held {time_held}s without SL/TP. "
                "Hostile liquidation."
            )
            market_close(pos, "ORPHAN_HOSTILE_LIQ")
            return

        # Instrument-safe ATR
        macro_atr = get_safe_atr(pos.symbol, 0.0, pos.price_open)
        is_buy    = (pos.type == mt5.ORDER_TYPE_BUY)
        curr      = tick.bid if is_buy else tick.ask

        # Fetch HMM state and multipliers
        oracle = self._oracle.get(pos.symbol)
        hmm_state = oracle.get("hmm_state", "NEUTRAL") if oracle else "NEUTRAL"
        sl_mult, tp_mult = get_atr_multipliers(pos.symbol, hmm_state)

        sl_dist = sl_mult * macro_atr
        min_tp_dist = 1.5 * sl_dist
        tp_dist = max(tp_mult * macro_atr, min_tp_dist)

        raw_sl = (pos.price_open - sl_dist) if is_buy else (pos.price_open + sl_dist)
        raw_tp = (pos.price_open + tp_dist) if is_buy else (pos.price_open - tp_dist)

        final_sl = normalize_stop(pos.symbol, curr, pos.sl if pos.sl != 0.0 else raw_sl, is_sl=True,  is_buy=is_buy)
        final_tp = normalize_stop(pos.symbol, curr, pos.tp if pos.tp != 0.0 else raw_tp, is_sl=False, is_buy=is_buy)

        res = mt5.order_send({
            "action": mt5.TRADE_ACTION_SLTP, "symbol": pos.symbol,
            "position": pos.ticket, "sl": final_sl, "tp": final_tp,
        })
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[NAKED_RESCUE] #{pos.ticket} {pos.symbol}: SL={final_sl:.5f} TP={final_tp:.5f}")
        else:
            code = res.retcode if res else "N/A"
            logger.warning(f"[NAKED_FAIL] #{pos.ticket} {pos.symbol}: {code}")

    def monitor_correlation_shock(self, positions: list):
        if not check_correlation_shock():
            return
            
        logger.warning("[SHOCK_DETECTOR] CORRELATION SHOCK DETECTED! Initiating proactive liquidation protocols.")
        
        for pos in positions:
            cluster = _get_cluster(pos.symbol)
            if cluster not in ["RISK_ON_CRYPTO", "RISK_ON_EQUITY", "RISK_ON_FX"]:
                continue
                
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                continue
            current_price = tick.bid if pos.type == 0 else tick.ask
            
            macro_atr = get_safe_atr(pos.symbol, 0.0, pos.price_open)
            
            if pos.type == 0:  # BUY
                tighter_sl = pos.price_open - 2.0 * macro_atr
                if current_price <= tighter_sl:
                    logger.critical(f"[SHOCK_BREACH_FATAL] BUY {pos.symbol} #{pos.ticket} price {current_price} <= tight SL {tighter_sl}. Executing failsafe MARKET_CLOSE.")
                    signal = FailsafeSignal(
                        ticket=pos.ticket,
                        symbol=pos.symbol,
                        action=FailsafeAction.MARKET_CLOSE,
                        trigger=f"SHOCK_BREACH_FATAL: Price {current_price} already below tight SL {tighter_sl}. FORCING MARKET CLOSE."
                    )
                    market_close(pos, reason="SHOCK_BREACH_FATAL")
                else:
                    logger.warning(f"[SHOCK_TIGHTEN] BUY {pos.symbol} #{pos.ticket} tightening SL to {tighter_sl}")
                    info = mt5.symbol_info(pos.symbol)
                    digits = info.digits if info else 5
                    tighter_sl_norm = normalize_stop(pos.symbol, current_price, tighter_sl, is_sl=True, is_buy=True)
                    tighter_sl_norm = round(tighter_sl_norm, digits)
                    
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": pos.symbol,
                        "position": pos.ticket,
                        "sl": float(tighter_sl_norm),
                        "tp": pos.tp
                    })
            else:  # SELL
                tighter_sl = pos.price_open + 2.0 * macro_atr
                if current_price >= tighter_sl:
                    logger.critical(f"[SHOCK_BREACH_FATAL] SELL {pos.symbol} #{pos.ticket} price {current_price} >= tight SL {tighter_sl}. Executing failsafe MARKET_CLOSE.")
                    signal = FailsafeSignal(
                        ticket=pos.ticket,
                        symbol=pos.symbol,
                        action=FailsafeAction.MARKET_CLOSE,
                        trigger=f"SHOCK_BREACH_FATAL: Price {current_price} already above tight SL {tighter_sl}. FORCING MARKET CLOSE."
                    )
                    market_close(pos, reason="SHOCK_BREACH_FATAL")
                else:
                    logger.warning(f"[SHOCK_TIGHTEN] SELL {pos.symbol} #{pos.ticket} tightening SL to {tighter_sl}")
                    info = mt5.symbol_info(pos.symbol)
                    digits = info.digits if info else 5
                    tighter_sl_norm = normalize_stop(pos.symbol, current_price, tighter_sl, is_sl=True, is_buy=False)
                    tighter_sl_norm = round(tighter_sl_norm, digits)
                    
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": pos.symbol,
                        "position": pos.ticket,
                        "sl": float(tighter_sl_norm),
                        "tp": pos.tp
                    })

    # ── Main Position Audit ───────────────────────────────────────────────────
    def _audit_positions(self, positions: list, config: dict):
        try:
            self.monitor_correlation_shock(positions)
        except Exception as shock_err:
            logger.error(f"[SHOCK_ERR] Error in monitor_correlation_shock: {shock_err}")

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

            # Update conviction history and peak
            ps.conviction_history.append(thesis_p)
            if len(ps.conviction_history) > 50:
                ps.conviction_history.pop(0)

            if ps.is_buy():
                ps.peak_price = max(ps.peak_price, current_price)
            else:
                ps.peak_price = min(ps.peak_price if ps.peak_price > 0 else current_price, current_price)

            profit_r_now    = ps.profit_r(current_price, macro_atr, sl_mult)
            ps.peak_profit_r = max(ps.peak_profit_r, profit_r_now)

            # H1 bars since entry
            h1_rates   = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, int(pos.time), broker_now + 3600)
            h1_candles = len(h1_rates) if h1_rates is not None else 0

            # Weekend pause (non-crypto only)
            is_crypto  = classify_symbol(symbol) == "CRYPTO"
            dt_now     = datetime.fromtimestamp(broker_now, tz=timezone.utc)
            is_weekend = (not is_crypto) and (
                (dt_now.weekday() == 4 and dt_now.strftime("%H:%M") >= "23:55") or
                dt_now.weekday() in [5, 6] or
                (dt_now.weekday() == 0 and dt_now.strftime("%H:%M") < "00:15")
            )

            # Sentiment
            sentiment = 0.0
            try:
                from gitagent_utils import fetch_unstructured_sentiment
                sentiment = fetch_unstructured_sentiment(symbol)
            except Exception:
                pass

            # Data density grace (first 10 minutes with thin data)
            rates_since = mt5.copy_rates_range(
                symbol, mt5.TIMEFRAME_M1, int(pos.time), broker_now + 60
            )
            trade_ticks = int(np.sum(rates_since["tick_volume"])) if rates_since is not None else 999
            data_sparse = (trade_ticks < 100) and ((broker_now - pos.time) < 600)

            # ── Profit Locking ────────────────────────────────────────────────
            self._apply_profit_locks(
                pos, ps, macro_atr, sl_mult, tp_mult, current_price, drawdown
            )

            # SWING TRADING NON-INTERFERENCE SHIELD
            # Position has NOT reached the 80% profit milestone.
            # It is CONSTITUTIONALLY FORBIDDEN from being modified by any secondary module.
            # Skip all early exit evaluations, divergence scale-outs, and event horizon shifts.
            initial_sl = getattr(ps, "initial_sl", 0.0)
            if initial_sl == 0.0:
                initial_sl = pos.price_open - (sl_mult * macro_atr) if ps.is_buy() else pos.price_open + (sl_mult * macro_atr)
            sl_dist = abs(pos.price_open - initial_sl)
            if sl_dist <= 0.0:
                sl_dist = sl_mult * macro_atr
            if sl_dist <= 0.0:
                sl_dist = 1.0
            min_tp_dist = 1.5 * sl_dist
            tp_dist = max(tp_mult * macro_atr, min_tp_dist)
            
            d_target = tp_dist
            d_guard = 0.80 * d_target
            d_current = abs(current_price - pos.price_open)
            
            is_in_profit = (pos.type == mt5.ORDER_TYPE_BUY and current_price > pos.price_open) or \
                           (pos.type == mt5.ORDER_TYPE_SELL and current_price < pos.price_open)
                           
            if not (is_in_profit and d_current >= d_guard):
                logger.info(f"[SWING_SHIELD] {symbol} #{pos.ticket} (d_current={d_current:.5f}, d_guard={d_guard:.5f}) protected by Non-Interference Shield.")
                continue

            # ── Event Horizon Protection (shielded secondary module) ──────────
            self._event_horizon_protection(pos, ps)

            # ── Divergence Scale-Out (runs outside profit lock to use live conviction) ──
            info = mt5.symbol_info(symbol)
            delta = ps.profit_delta(current_price)
            if (not ps.divergence_done and
                    delta >= 2.5 * macro_atr and
                    thesis_p < 0.65 and tick and info):
                if safe_scale_out(pos, ps, 0.50, "DIVERGENCE_SCALE_50PCT", info, tick):
                    ps.divergence_done = True

            # ── Exit Scoring ──────────────────────────────────────────────────
            if not data_sparse:
                exit_sig = compute_exit_score(
                    ps=ps, oracle=oracle, current_price=current_price,
                    macro_atr=macro_atr, sl_mult=sl_mult, live_p=live_p,
                    config=config, sentiment=sentiment,
                    broker_now=broker_now, h1_candles=h1_candles,
                    is_weekend_pause=is_weekend,
                )
            else:
                logger.info(
                    f"[DATA_GRACE] {symbol} #{pos.ticket}: "
                    f"{trade_ticks} ticks < 100 in first 10 min — exits suppressed."
                )
                exit_sig = ExitSignal()

            should_exit = exit_sig.hard_exit or (exit_sig.score >= EXIT_SCORE_THRESHOLD)

            if should_exit:
                reason = (
                    f"{exit_sig.reason_primary} | "
                    f"{' | '.join(exit_sig.reasons)} | "
                    f"R={profit_r_now:.2f} | peak_R={ps.peak_profit_r:.2f} | "
                    f"PnL={pos.profit:+.2f}"
                )
                logger.warning(f"[SRE_EXIT] {symbol} #{pos.ticket}: {reason}")

                # Execution deduplication [ARCH FIX]
                ps.liquidation_sent    = True
                ps.last_liquidation_ts = now

                push_exit_signal(pos, reason)
                success = market_close(pos, "SRE_LIQUIDATION")

                if not success:
                    ps.liquidation_sent = False   # Reset for retry next cycle
                else:
                    # Diagnostic ticket
                    diag = {
                        "event":        exit_sig.reason_primary,
                        "symbol":       symbol,
                        "ticket":       pos.ticket,
                        "direction":    "BUY" if ps.is_buy() else "SELL",
                        "hmm_state":    hmm_state,
                        "live_p":       live_p,
                        "exit_score":   round(exit_sig.score, 4),
                        "pnl":          round(pos.profit, 2),
                        "r_multiple":   round(profit_r_now, 3),
                        "peak_r":       round(ps.peak_profit_r, 3),
                        "timestamp":    int(now),
                        "version":      "v25.0",
                    }
                    diag_path = DIAG_DIR / f"exit_{symbol}_{int(now)}.json"
                    try:
                        from filelock import FileLock
                        with FileLock(str(diag_path) + ".lock"):
                            with open(diag_path, "w") as fh:
                                json.dump(diag, fh, indent=2)
                    except Exception as e:
                        logger.warning(f"[DIAG_WRITE_ERR] {e}")
            else:
                logger.debug(
                    f"[OK] {symbol} #{pos.ticket}: score={exit_sig.score:.2f} | "
                    f"R={profit_r_now:.2f} | HMM={hmm_state} | thesis_p={thesis_p:.3f}"
                )

    # ── Monitor Loop ──────────────────────────────────────────────────────────
    def monitor_loop(self):
        logger.info("Monitor loop started — PSR audit every 10 min | scan every 1 s.")
        last_audit = 0.0

        while True:
            try:
                if time.time() - last_audit > 600:
                    self.audit_performance()
                    last_audit = time.time()

                sentinel_pos  = mt5.positions_get(magic=MAGIC_NUMBER)  or []
                legacy_pos    = mt5.positions_get(magic=MAGIC_LEGACY)  or []
                all_positions = list(sentinel_pos) + list(legacy_pos)
                import requests
                for pos in all_positions:
                    if pos.sl > 0.0 or pos.tp > 0.0:
                        print(f"[CONSTITUTIONAL_VIOLATION] Physical stops detected on ticket {pos.ticket}. Stripping immediately.")
                        try:
                            requests.post("http://127.0.0.1:8000/strip_stops", json={"ticket": pos.ticket}, timeout=5)
                        except Exception as e:
                            print(f"[STRIP_STOPS_FAIL] Could not strip stops on {pos.ticket}: {e}")

                active_tickets = {p.ticket for p in all_positions}

                # State cleanup [ARCH FIX] — prevents ticket reuse state corruption
                self._cleanup_closed_states(active_tickets)

                config = load_risk_config()

                active_audit_positions = []
                for pos in all_positions:
                    ps = self._get_state(pos)
                    
                    # Naked sweep for orphaned SL/TP
                    if pos.tp == 0.0 or pos.sl == 0.0:
                        self._naked_sweep(pos)
                    
                    active_audit_positions.append(pos)

                if active_audit_positions:
                    self._audit_positions(active_audit_positions, config)

                time.sleep(1)

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
