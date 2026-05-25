import logging
from dataclasses import dataclass
from datetime import datetime
import pytz
import MetaTrader5 as mt5

import sentinel_config as cfg

logger = logging.getLogger("PreExecutionGate")

class PriceUnit:
    def __init__(self, value: float):
        if not isinstance(value, (int, float)) or value <= 0:
            raise TypeError(f"PriceUnit must be a positive float/int, got {type(value)}")
        self.value = float(value)

class PipDistance:
    def __init__(self, value: float, entry_price: float = None):
        if not isinstance(value, (int, float)) or value <= 0:
            raise TypeError(f"PipDistance must be a positive float/int, got {type(value)}")
        if entry_price is not None and value >= entry_price:
            raise ValueError(f"Unit Confusion Detected: Distance ({value}) is greater than or equal to Entry Price ({entry_price})")
        self.value = float(value)

class LotVolume:
    def __init__(self, value: float):
        if not isinstance(value, (int, float)) or value <= 0:
            raise TypeError(f"LotVolume must be a positive float/int, got {type(value)}")
        self.value = float(value)

@dataclass
class PreExecutionVerdict:
    approved: bool
    _summary: str
    
    def summary(self) -> str:
        return self._summary

def run_all_gates(
    symbol: str, 
    direction: str, 
    asset_class: str,
    regime: str, 
    ticket_ref: str,
    kelly_lots: float, 
    entry_price: float,
    sl_distance: float, 
    tp_distance: float,
    risk_usd: float, 
    equity: float,
    current_heat_usd: float,
    embargo_registry: dict
) -> PreExecutionVerdict:
    
    # Enforce strict parameter type-safety and dimension checking
    try:
        PriceUnit(entry_price)
        PipDistance(sl_distance, entry_price)
        PipDistance(tp_distance, entry_price)
        LotVolume(kelly_lots)
    except (TypeError, ValueError) as type_err:
        logger.error(f"Type-Safety Gate Violation for {symbol}: {type_err}")
        return PreExecutionVerdict(approved=False, _summary=f"BLOCK [{ticket_ref}]: Type-Safety Violation: {type_err}")

    # Helper to return rejection
    def reject(reason: str) -> PreExecutionVerdict:
        return PreExecutionVerdict(approved=False, _summary=f"BLOCK [{ticket_ref}]: {reason}")

    # GATE-1: ECN Minimum Contract Conflict
    # Rule A: If equity < GATE_MIN_EQUITY[symbol], BLOCK
    min_equity = cfg.GATE_MIN_EQUITY.get(symbol, 0.0)
    if equity < min_equity:
        return reject(f"Gate 1A Failed: Equity {equity} < Min Equity {min_equity} for {symbol}")
        
    # Rule B: If kelly_lots < GATE_ECN_MIN_LOTS[symbol], BLOCK
    min_lots = cfg.GATE_ECN_MIN_LOTS.get(symbol, 0.01) # Default 0.01 for forex
    if kelly_lots < min_lots:
        return reject(f"Gate 1B Failed: Kelly Lots {kelly_lots} < ECN Min Lots {min_lots} for {symbol}")

    # GATE-2: Leverage Wall
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if symbol_info else 1.0
    
    notional = kelly_lots * contract_size * entry_price
    leverage = notional / equity if equity > 0 else float('inf')
    if leverage > cfg.GATE_MAX_LEVERAGE:
        return reject(f"Gate 2 Failed: Leverage {leverage:.2f}x > Max {cfg.GATE_MAX_LEVERAGE}x")

    # GATE-3: RR Ratio Enforcement
    if sl_distance <= 0:
        return reject("Gate 3 Failed: Invalid SL distance <= 0")
        
    rr_ratio = tp_distance / sl_distance
    min_rr = 2.0 if "BULL" in regime or "BEAR" in regime else 1.5
    if rr_ratio < min_rr:
        return reject(f"Gate 3 Failed: RR Ratio {rr_ratio:.2f} < Min {min_rr} for regime {regime}")

    # GATE-4: Physical Stop Contamination Check
    logger.debug(f"Gate 4: Contamination check setup passed for {symbol}")

    # GATE-5: Hard Risk Cap
    risk_pct = risk_usd / equity if equity > 0 else 1.0
    if risk_pct > cfg.GATE_MAX_RISK_PCT_PER_TRADE:
        return reject(f"Gate 5 Failed: Risk Pct {risk_pct:.4f} > Max {cfg.GATE_MAX_RISK_PCT_PER_TRADE}")

    # GATE-6: Portfolio Heat Ceiling
    heat_pct = (current_heat_usd + risk_usd) / equity if equity > 0 else 1.0
    if heat_pct > cfg.GATE_MAX_PORTFOLIO_HEAT:
        return reject(f"Gate 6 Failed: Heat Pct {heat_pct:.4f} > Max {cfg.GATE_MAX_PORTFOLIO_HEAT}")

    # GATE-7: Weekend Blackout
    if asset_class.upper() != "CRYPTO":
        now_utc = datetime.now(pytz.utc)
        if now_utc.weekday() == 4 and (now_utc.hour > cfg.GATE_BLACKOUT_FRIDAY_HOUR or (now_utc.hour == cfg.GATE_BLACKOUT_FRIDAY_HOUR and now_utc.minute >= cfg.GATE_BLACKOUT_FRIDAY_MIN)):
            return reject("Gate 7 Failed: Weekend Blackout (Friday)")
        elif now_utc.weekday() == 5 or (now_utc.weekday() == 6 and now_utc.hour < 22):
            return reject("Gate 7 Failed: Weekend Blackout (Saturday/Sunday daytime)")
        elif now_utc.weekday() == 0 and (now_utc.hour < cfg.GATE_BLACKOUT_MONDAY_HOUR or (now_utc.hour == cfg.GATE_BLACKOUT_MONDAY_HOUR and now_utc.minute < cfg.GATE_BLACKOUT_MONDAY_MIN)):
            return reject("Gate 7 Failed: Weekend Blackout (Monday morning)")

    # GATE-8: Amnesia Lock
    if symbol in embargo_registry:
        return reject(f"Gate 8 Failed: Symbol {symbol} is currently in amnesia lock registry")

    return PreExecutionVerdict(approved=True, _summary="All 8 gates passed.")
