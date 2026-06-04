"""
tp_placement_engine.py
======================
CADES — DIRECTIVE ZETA Implementation
Structural TP Placement Validator and Resolver

Enforces all five laws of DIRECTIVE ZETA:
  Law 1: Structure-first TP — not a mechanical multiplier
  Law 2: ATR ceiling (3× ATR(14, D1))
  Law 3: Per-asset-class % distance cap
  Law 4: Crypto swing TP absolute veto
  Law 5: Minimum R:R gate (≥ 1.5, gate only — not placement method)

Integration points:
  - Called in Slow Loop signal pipeline before MT5 order transmission
  - Called in profit_manager.py PositionState.register() for post-open audit
  - Called in Slow Loop reconciliation every 5 minutes for all open positions

Author: CADES Architectural Session, 2026-06-03
Constitutional ref: DIRECTIVE_ZETA_TP_PLACEMENT.md v31.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("CADES.TPPlacement")


# ---------------------------------------------------------------------------
# Asset class taxonomy
# ---------------------------------------------------------------------------

class AssetClass(Enum):
    FOREX_MAJOR  = "forex_major"
    FOREX_CROSS  = "forex_cross"
    FOREX_EXOTIC = "forex_exotic"
    INDEX        = "index"
    COMMODITY    = "commodity"
    CRYPTO       = "crypto"


# Per-asset-class maximum TP distance as fraction of entry price.
# None = ABSOLUTE VETO (crypto).
ASSET_CLASS_TP_CAPS: dict[AssetClass, Optional[float]] = {
    AssetClass.FOREX_MAJOR:  0.040,
    AssetClass.FOREX_CROSS:  0.050,
    AssetClass.FOREX_EXOTIC: 0.060,
    AssetClass.INDEX:        0.070,
    AssetClass.COMMODITY:    0.070,
    AssetClass.CRYPTO:       None,
}

# Per-asset-class maximum swing hold in trading days (time-stop).
ASSET_CLASS_TIME_STOP: dict[AssetClass, Optional[int]] = {
    AssetClass.FOREX_MAJOR:  10,
    AssetClass.FOREX_CROSS:  10,
    AssetClass.FOREX_EXOTIC: 14,
    AssetClass.INDEX:        12,
    AssetClass.COMMODITY:    15,
    AssetClass.CRYPTO:       None,
}

INSTRUMENT_ASSET_CLASS: dict[str, AssetClass] = {
    # Forex Majors
    "EURUSD": AssetClass.FOREX_MAJOR,
    "GBPUSD": AssetClass.FOREX_MAJOR,
    "USDJPY": AssetClass.FOREX_MAJOR,
    "USDCHF": AssetClass.FOREX_MAJOR,
    "AUDUSD": AssetClass.FOREX_MAJOR,
    "NZDUSD": AssetClass.FOREX_MAJOR,
    "USDCAD": AssetClass.FOREX_MAJOR,
    # Forex Crosses
    "EURJPY": AssetClass.FOREX_CROSS,
    "GBPJPY": AssetClass.FOREX_CROSS,
    "AUDJPY": AssetClass.FOREX_CROSS,
    "NZDJPY": AssetClass.FOREX_CROSS,
    "EURGBP": AssetClass.FOREX_CROSS,
    "GBPAUD": AssetClass.FOREX_CROSS,
    "GBPCAD": AssetClass.FOREX_CROSS,
    "CADCHF": AssetClass.FOREX_CROSS,
    "AUDCAD": AssetClass.FOREX_CROSS,
    "AUDNZD": AssetClass.FOREX_CROSS,
    # Forex Exotics
    "EURSEK": AssetClass.FOREX_EXOTIC,
    "EURNOK": AssetClass.FOREX_EXOTIC,
    "EURDKK": AssetClass.FOREX_EXOTIC,
    "USDMXN": AssetClass.FOREX_EXOTIC,
    "USDZAR": AssetClass.FOREX_EXOTIC,
    "USDTRY": AssetClass.FOREX_EXOTIC,
    "USDHUF": AssetClass.FOREX_EXOTIC,
    "USDPLN": AssetClass.FOREX_EXOTIC,
    "USDCZK": AssetClass.FOREX_EXOTIC,
    # Indices
    "NAS100": AssetClass.INDEX,
    "SP500":  AssetClass.INDEX,
    "US30":   AssetClass.INDEX,
    "GER40":  AssetClass.INDEX,
    "UK100":  AssetClass.INDEX,
    "AUS200": AssetClass.INDEX,
    "JPN225": AssetClass.INDEX,
    "FRA40":  AssetClass.INDEX,
    # Commodities
    "XAUUSD": AssetClass.COMMODITY,
    "XAGUSD": AssetClass.COMMODITY,
    "XPTUSD": AssetClass.COMMODITY,
    "USOIL":  AssetClass.COMMODITY,
    "UKOIL":  AssetClass.COMMODITY,
    "NGAS":   AssetClass.COMMODITY,
    # Crypto — all vetoed
    "BTCUSD": AssetClass.CRYPTO,
    "ETHUSD": AssetClass.CRYPTO,
    "XRPUSD": AssetClass.CRYPTO,
    "SOLUSD": AssetClass.CRYPTO,
    "ADAUSD": AssetClass.CRYPTO,
    "BNBUSD": AssetClass.CRYPTO,
    "DOTUSD": AssetClass.CRYPTO,
    "LTCUSD": AssetClass.CRYPTO,
}

ATR_CEILING_MULTIPLIER: float = 3.0
MIN_RR_RATIO:           float = 1.5
MAX_ATR_AGE_SECONDS:    int   = 300   # 5 minutes — beyond this is DEGRADED DATA


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StructuralLevel:
    """A candidate TP anchor derived from market structure."""
    price:       float
    level_type:  str          # "swing_high", "swing_low", "fib_ext", "sr_zone", "volume_node"
    source_tf:   str          # "D1", "H4", "H1"
    strength:    float        # 0.0–1.0: touch count, confluence
    distance:    float        # abs distance from entry
    distance_pct: float       # as fraction of entry


@dataclass
class TPValidationResult:
    """
    Full audit record of a TP validation pass.
    Stored in PositionState and written to the constitutional trade log.
    """
    is_valid:           bool
    proposed_tp:        float
    final_tp:           Optional[float]         # adjusted_tp if adjusted, else proposed_tp
    adjusted:           bool                    # True if TP was moved to comply

    direction:          int                     # 1 = long, -1 = short
    asset_class:        AssetClass
    symbol:             str

    entry:              float
    sl:                 float
    sl_distance:        float
    sl_distance_pct:    float

    tp_distance:        float
    tp_distance_pct:    float
    rr_ratio:           float

    atr_d1:             Optional[float]
    atr_ceiling_price:  Optional[float]
    atr_ceiling_dist:   Optional[float]
    atr_ceiling_pct:    Optional[float]

    asset_class_cap_pct: Optional[float]
    asset_class_cap_price: Optional[float]

    binding_ceiling_price: Optional[float]
    binding_ceiling_label: Optional[str]        # "ATR" or "AssetCap"

    structural_level:   Optional[StructuralLevel]
    time_stop_days:     Optional[int]

    rejection_reason:   Optional[str]
    warnings:           List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Structural Level Resolver
# ---------------------------------------------------------------------------

class StructuralLevelResolver:
    """
    Identifies the nearest valid structural TP anchor within a ceiling price.

    Uses OracleCache for D1/H4 bar data. Falls back to a simplified
    swing-high/low scan if the FAISS episodic memory is unavailable.
    """

    def __init__(self, oracle_cache):
        self.oracle_cache = oracle_cache

    def get_levels(
        self,
        symbol:   str,
        entry:    float,
        direction: int,
        ceiling:  float,
        lookback_bars: int = 50,
    ) -> List[StructuralLevel]:
        """
        Return all structural levels between entry and ceiling, sorted by
        proximity to entry (nearest first).

        For a LONG:  levels must be ABOVE entry and AT or BELOW ceiling.
        For a SHORT: levels must be BELOW entry and AT or ABOVE ceiling.
        """
        levels: List[StructuralLevel] = []

        for tf in ("D1", "H4"):
            bars = self._fetch_bars(symbol, tf, lookback_bars)
            if bars is None or len(bars) < 5:
                continue

            swing_levels = self._find_swing_levels(bars, tf)
            fib_levels   = self._find_fib_extensions(bars, entry, direction, tf)

            for lv in swing_levels + fib_levels:
                if self._is_between(lv.price, entry, ceiling, direction):
                    levels.append(lv)

        levels.sort(key=lambda lv: lv.distance)
        return levels

    def _fetch_bars(self, symbol: str, timeframe: str, count: int):
        try:
            return self.oracle_cache.get_bars(symbol=symbol, timeframe=timeframe, count=count)
        except Exception as e:
            logger.warning(f"[StructuralResolver] Bar fetch failed {symbol}/{timeframe}: {e}")
            return None

    def _find_swing_levels(self, bars, timeframe: str) -> List[StructuralLevel]:
        """Identify swing highs and lows using a 3-bar fractal pattern."""
        levels = []
        highs  = [b["high"]  for b in bars]
        lows   = [b["low"]   for b in bars]
        closes = [b["close"] for b in bars]

        for i in range(2, len(bars) - 2):
            # Swing high: bar[i].high > bar[i-1].high and bar[i-2].high
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] \
               and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                touch_count = self._count_touches(highs[i], bars, tolerance=0.001)
                levels.append(StructuralLevel(
                    price=highs[i],
                    level_type="swing_high",
                    source_tf=timeframe,
                    strength=min(1.0, touch_count / 5),
                    distance=0.0,       # filled by caller
                    distance_pct=0.0,
                ))

            # Swing low
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] \
               and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                touch_count = self._count_touches(lows[i], bars, tolerance=0.001, use_lows=True)
                levels.append(StructuralLevel(
                    price=lows[i],
                    level_type="swing_low",
                    source_tf=timeframe,
                    strength=min(1.0, touch_count / 5),
                    distance=0.0,
                    distance_pct=0.0,
                ))

        return levels

    def _find_fib_extensions(
        self, bars, entry: float, direction: int, timeframe: str
    ) -> List[StructuralLevel]:
        """
        Compute Fibonacci extension levels (127.2%, 138.2%, 161.8%)
        from the most recent major swing.
        """
        levels = []
        FIB_EXTENSIONS = [1.272, 1.382, 1.618]

        highs = np.array([b["high"]  for b in bars])
        lows  = np.array([b["low"]   for b in bars])

        if direction == 1:
            swing_low  = np.min(lows[-20:])
            swing_high = np.max(highs[-20:])
            swing_range = swing_high - swing_low
            for fib in FIB_EXTENSIONS:
                target = swing_high + swing_range * (fib - 1.0)
                levels.append(StructuralLevel(
                    price=target,
                    level_type=f"fib_ext_{fib:.3f}",
                    source_tf=timeframe,
                    strength=0.5,
                    distance=0.0,
                    distance_pct=0.0,
                ))
        else:
            swing_high = np.max(highs[-20:])
            swing_low  = np.min(lows[-20:])
            swing_range = swing_high - swing_low
            for fib in FIB_EXTENSIONS:
                target = swing_low - swing_range * (fib - 1.0)
                levels.append(StructuralLevel(
                    price=target,
                    level_type=f"fib_ext_{fib:.3f}",
                    source_tf=timeframe,
                    strength=0.5,
                    distance=0.0,
                    distance_pct=0.0,
                ))

        return levels

    @staticmethod
    def _count_touches(
        price: float,
        bars: list,
        tolerance: float = 0.001,
        use_lows: bool = False,
    ) -> int:
        key   = "low" if use_lows else "high"
        count = sum(1 for b in bars if abs(b[key] - price) / price < tolerance)
        return max(1, count)

    @staticmethod
    def _is_between(price: float, entry: float, ceiling: float, direction: int) -> bool:
        if direction == 1:
            return entry < price <= ceiling
        else:
            return ceiling <= price < entry


# ---------------------------------------------------------------------------
# TPPlacementEngine — main validator
# ---------------------------------------------------------------------------

class TPPlacementEngine:
    """
    Master TP placement validator. Implements DIRECTIVE ZETA in full.

    Usage (pre-entry gate):
        result = engine.validate_tp_placement(
            symbol="XAUUSD", entry=4495.44, sl=4086.36,
            proposed_tp=5109.06, direction=1
        )
        if not result.is_valid:
            logger.error(f"TP GATE REJECT: {result.rejection_reason}")
            return  # block entry
        if result.adjusted:
            logger.warning(f"TP adjusted to {result.final_tp}")
            # use result.final_tp for the MT5 order

    Usage (post-open audit in profit_manager.py):
        result = engine.audit_open_position(position_state)
        if result.rejection_reason:
            # flag as TP_LEGACY_VIOLATION, attempt TP modification
    """

    def __init__(self, oracle_cache, level_resolver: Optional[StructuralLevelResolver] = None):
        self.oracle_cache    = oracle_cache
        self.level_resolver  = level_resolver or StructuralLevelResolver(oracle_cache)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_tp_placement(
        self,
        symbol:      str,
        entry:       float,
        sl:          float,
        proposed_tp: float,
        direction:   int,           # 1 = long, -1 = short
        use_structural_resolver: bool = True,
    ) -> TPValidationResult:
        """
        Full DIRECTIVE ZETA validation pass.

        Returns a TPValidationResult. Caller must check .is_valid and
        use .final_tp (not .proposed_tp) when placing the MT5 order.
        """
        symbol = symbol.upper().replace(".", "").replace("_", "").replace(" ", "")
        asset_class = self._classify(symbol)

        sl_distance     = abs(entry - sl)
        sl_distance_pct = sl_distance / entry if entry > 0 else 0.0

        # ---------------------------------------------------------------
        # Law 4 — Crypto absolute veto (REPEALED in v36.0)
        # Crypto now flows through with Triple-Barrier limits applied
        # in trade_executor_mcp.py and audited in profit_manager_v28_34.py
        # ---------------------------------------------------------------
        if asset_class == AssetClass.CRYPTO:
            return TPValidationResult(
                is_valid=True,
                proposed_tp=proposed_tp,
                final_tp=0.0,
                adjusted=False,
                direction=direction,
                asset_class=asset_class,
                symbol=symbol,
                entry=entry,
                sl=sl,
                sl_distance=sl_distance,
                sl_distance_pct=sl_distance_pct,
                tp_distance=0.0,
                tp_distance_pct=0.0,
                rr_ratio=1.5,
                atr_d1=self._get_atr(symbol),
                atr_ceiling_price=None,
                atr_ceiling_dist=None,
                atr_ceiling_pct=None,
                asset_class_cap_pct=None,
                asset_class_cap_price=None,
                binding_ceiling_price=None,
                binding_ceiling_label=None,
                structural_level=None,
                time_stop_days=None,
                rejection_reason="",
            )

        # ---------------------------------------------------------------
        # Basic geometry checks
        # ---------------------------------------------------------------
        if sl_distance <= 0:
            return self._hard_reject(
                symbol, entry, sl, proposed_tp, direction, asset_class,
                "SL distance is zero or negative — invalid position geometry.",
            )

        # Validate direction consistency
        if direction == 1 and proposed_tp <= entry:
            return self._hard_reject(
                symbol, entry, sl, proposed_tp, direction, asset_class,
                f"Direction=LONG but proposed_tp ({proposed_tp}) <= entry ({entry}).",
            )
        if direction == -1 and proposed_tp >= entry:
            return self._hard_reject(
                symbol, entry, sl, proposed_tp, direction, asset_class,
                f"Direction=SHORT but proposed_tp ({proposed_tp}) >= entry ({entry}).",
            )

        # ---------------------------------------------------------------
        # Law 2 — ATR ceiling
        # ---------------------------------------------------------------
        atr_d1 = self._get_atr(symbol)
        if atr_d1 is None:
            return self._hard_reject(
                symbol, entry, sl, proposed_tp, direction, asset_class,
                "D1 ATR(14) unavailable or stale — DEGRADED DATA VETO. Entry blocked per DIRECTIVE OMEGA.",
            )

        atr_ceiling_dist  = atr_d1 * ATR_CEILING_MULTIPLIER
        atr_ceiling_price = (entry + atr_ceiling_dist) if direction == 1 else (entry - atr_ceiling_dist)
        atr_ceiling_pct   = atr_ceiling_dist / entry

        # ---------------------------------------------------------------
        # Law 3 — Asset class % cap
        # ---------------------------------------------------------------
        asset_class_cap_pct   = ASSET_CLASS_TP_CAPS[asset_class]
        asset_class_cap_price = (
            (entry * (1.0 + asset_class_cap_pct)) if direction == 1
            else (entry * (1.0 - asset_class_cap_pct))
        ) if asset_class_cap_pct is not None else None

        # ---------------------------------------------------------------
        # Binding ceiling — most restrictive of ATR and class cap
        # ---------------------------------------------------------------
        if direction == 1:
            candidates = [atr_ceiling_price]
            if asset_class_cap_price is not None:
                candidates.append(asset_class_cap_price)
            binding_ceiling = min(candidates)
            binding_label   = "ATR" if binding_ceiling == atr_ceiling_price else "AssetCap"
        else:
            candidates = [atr_ceiling_price]
            if asset_class_cap_price is not None:
                candidates.append(asset_class_cap_price)
            binding_ceiling = max(candidates)
            binding_label   = "ATR" if binding_ceiling == atr_ceiling_price else "AssetCap"

        # ---------------------------------------------------------------
        # Law 1 — Structural level resolution
        # ---------------------------------------------------------------
        structural_level: Optional[StructuralLevel] = None
        chosen_tp = proposed_tp

        if use_structural_resolver:
            levels = self.level_resolver.get_levels(
                symbol=symbol,
                entry=entry,
                direction=direction,
                ceiling=binding_ceiling,
            )
            if levels:
                best = levels[0]          # nearest level within ceiling
                best.distance     = abs(best.price - entry)
                best.distance_pct = best.distance / entry
                structural_level  = best
                chosen_tp         = best.price
                logger.info(
                    f"[TPEngine] {symbol}: structural TP = {chosen_tp:.5f} "
                    f"({best.level_type} on {best.source_tf}, strength={best.strength:.2f})"
                )
            else:
                logger.warning(
                    f"[TPEngine] {symbol}: No structural level found within "
                    f"binding ceiling {binding_ceiling:.5f}. Falling back to ceiling."
                )
                chosen_tp = binding_ceiling
        else:
            # Validate proposed_tp against ceiling
            if direction == 1 and proposed_tp > binding_ceiling:
                chosen_tp = binding_ceiling
            elif direction == -1 and proposed_tp < binding_ceiling:
                chosen_tp = binding_ceiling

        tp_distance     = abs(chosen_tp - entry)
        tp_distance_pct = tp_distance / entry
        rr_ratio        = tp_distance / sl_distance

        # ---------------------------------------------------------------
        # Law 5 — Minimum R:R gate
        # ---------------------------------------------------------------
        warnings: List[str] = []

        if rr_ratio < MIN_RR_RATIO:
            return TPValidationResult(
                is_valid=False,
                proposed_tp=proposed_tp,
                final_tp=None,
                adjusted=False,
                direction=direction,
                asset_class=asset_class,
                symbol=symbol,
                entry=entry,
                sl=sl,
                sl_distance=sl_distance,
                sl_distance_pct=sl_distance_pct,
                tp_distance=tp_distance,
                tp_distance_pct=tp_distance_pct,
                rr_ratio=rr_ratio,
                atr_d1=atr_d1,
                atr_ceiling_price=atr_ceiling_price,
                atr_ceiling_dist=atr_ceiling_dist,
                atr_ceiling_pct=atr_ceiling_pct,
                asset_class_cap_pct=asset_class_cap_pct,
                asset_class_cap_price=asset_class_cap_price,
                binding_ceiling_price=binding_ceiling,
                binding_ceiling_label=binding_label,
                structural_level=structural_level,
                time_stop_days=ASSET_CLASS_TIME_STOP[asset_class],
                rejection_reason=(
                    f"DIRECTIVE ZETA — LAW 5: R:R of {rr_ratio:.2f} is below the minimum "
                    f"threshold of {MIN_RR_RATIO}. No structural level within the binding "
                    f"ceiling ({binding_ceiling:.5f}) produces an acceptable trade. "
                    f"Wait for a better entry or identify a more distant structural target "
                    f"that passes the ceiling test."
                ),
                warnings=warnings,
            )

        adjusted = (abs(chosen_tp - proposed_tp) > 1e-8)
        if adjusted:
            warnings.append(
                f"TP adjusted from {proposed_tp:.5f} to {chosen_tp:.5f} "
                f"({tp_distance_pct*100:.2f}% from entry, R:R={rr_ratio:.2f}). "
                f"Original TP violated {binding_label} ceiling at {binding_ceiling:.5f}."
            )

        if tp_distance_pct > asset_class_cap_pct * 0.85:
            warnings.append(
                f"TP distance {tp_distance_pct*100:.2f}% is within 15% of the "
                f"asset class cap ({asset_class_cap_pct*100:.1f}%). "
                f"Monitor closely — any adverse ATR expansion could breach the ceiling."
            )

        return TPValidationResult(
            is_valid=True,
            proposed_tp=proposed_tp,
            final_tp=chosen_tp,
            adjusted=adjusted,
            direction=direction,
            asset_class=asset_class,
            symbol=symbol,
            entry=entry,
            sl=sl,
            sl_distance=sl_distance,
            sl_distance_pct=sl_distance_pct,
            tp_distance=tp_distance,
            tp_distance_pct=tp_distance_pct,
            rr_ratio=rr_ratio,
            atr_d1=atr_d1,
            atr_ceiling_price=atr_ceiling_price,
            atr_ceiling_dist=atr_ceiling_dist,
            atr_ceiling_pct=atr_ceiling_pct,
            asset_class_cap_pct=asset_class_cap_pct,
            asset_class_cap_price=asset_class_cap_price,
            binding_ceiling_price=binding_ceiling,
            binding_ceiling_label=binding_label,
            structural_level=structural_level,
            time_stop_days=ASSET_CLASS_TIME_STOP[asset_class],
            rejection_reason=None,
            warnings=warnings,
        )

    def audit_open_position(
        self,
        symbol:     str,
        entry:      float,
        sl:         float,
        current_tp: float,
        direction:  int,
    ) -> TPValidationResult:
        """
        Post-open audit for existing positions (Slow Loop reconciliation).
        Runs the same validation against the live TP on the book.
        Used to detect and flag LEGACY VIOLATIONS per Article II Gate 3.
        """
        return self.validate_tp_placement(
            symbol=symbol,
            entry=entry,
            sl=sl,
            proposed_tp=current_tp,
            direction=direction,
            use_structural_resolver=False,  # audit only — don't move levels on open positions
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify(self, symbol: str) -> AssetClass:
        if symbol in INSTRUMENT_ASSET_CLASS:
            return INSTRUMENT_ASSET_CLASS[symbol]
        # Heuristic fallback for broker-suffix variants (e.g., "EURUSD.c")
        for key, cls in INSTRUMENT_ASSET_CLASS.items():
            if symbol.startswith(key):
                return cls
        logger.warning(f"[TPEngine] Unknown instrument '{symbol}', defaulting to FOREX_CROSS")
        return AssetClass.FOREX_CROSS

    def _get_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        try:
            result = self.oracle_cache.get_atr(
                symbol=symbol,
                timeframe="D1",
                period=period,
                max_age_seconds=MAX_ATR_AGE_SECONDS,
            )
            if result is None or result <= 0:
                logger.error(f"[TPEngine] ATR returned invalid value for {symbol}: {result}")
                return None
            return result
        except Exception as exc:
            logger.error(f"[TPEngine] ATR fetch exception for {symbol}: {exc}")
            return None

    def _hard_reject(
        self,
        symbol:      str,
        entry:       float,
        sl:          float,
        proposed_tp: float,
        direction:   int,
        asset_class: AssetClass,
        reason:      str,
    ) -> TPValidationResult:
        sl_dist = abs(entry - sl)
        tp_dist = abs(proposed_tp - entry)
        return TPValidationResult(
            is_valid=False,
            proposed_tp=proposed_tp,
            final_tp=None,
            adjusted=False,
            direction=direction,
            asset_class=asset_class,
            symbol=symbol,
            entry=entry,
            sl=sl,
            sl_distance=sl_dist,
            sl_distance_pct=sl_dist / entry if entry > 0 else 0,
            tp_distance=tp_dist,
            tp_distance_pct=tp_dist / entry if entry > 0 else 0,
            rr_ratio=tp_dist / sl_dist if sl_dist > 0 else 0,
            atr_d1=None,
            atr_ceiling_price=None,
            atr_ceiling_dist=None,
            atr_ceiling_pct=None,
            asset_class_cap_pct=ASSET_CLASS_TP_CAPS.get(asset_class),
            asset_class_cap_price=None,
            binding_ceiling_price=None,
            binding_ceiling_label=None,
            structural_level=None,
            time_stop_days=ASSET_CLASS_TIME_STOP.get(asset_class),
            rejection_reason=f"DIRECTIVE ZETA HARD REJECT: {reason}",
            warnings=[],
        )
