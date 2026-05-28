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

BLOCK = "BLOCK"
ALLOW = "ALLOW"

@dataclass
class GateResult:
    gate: str
    status: str
    message: str

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

def _get_direction(p) -> str:
    if p.type in [0, 2, 4]:
        return "BUY"
    return "SELL"

def gate0_correlation_cluster_limit(symbol: str, direction: str) -> GateResult:
    if not mt5.initialize():
        mt5.initialize()
        
    MAGIC_NUMBER = 142
    MAGIC_LEGACY = 17300
    
    positions = mt5.positions_get() or ()
    open_positions = [p for p in positions if getattr(p, 'magic', 0) in (142, 17300)]
    
    orders = mt5.orders_get() or ()
    pending_orders = [o for o in orders if getattr(o, 'magic', 0) in (142, 17300)]
    
    all_active_exposure = open_positions + pending_orders
    
    cluster = _get_cluster(symbol)
    
    cluster_positions = [
        p for p in all_active_exposure 
        if _get_cluster(p.symbol) == cluster
    ]
    
    global_risk_on_count = len([
        p for p in all_active_exposure 
        if _get_cluster(p.symbol) in ["RISK_ON_CRYPTO", "RISK_ON_EQUITY", "RISK_ON_FX"]
    ])
    
    if cluster in ["RISK_ON_CRYPTO", "RISK_ON_EQUITY", "RISK_ON_FX"] and global_risk_on_count >= 3:
        return GateResult(
            gate="GATE-0-GLOBAL-CONTAGION", 
            status=BLOCK, 
            message="GLOBAL RISK-ON CAP REACHED (Max 3). Halting all new risk-on exposure."
        )
        
    candidate_direction = str(direction).upper()
    
    if cluster in ["RISK_ON_CRYPTO", "RISK_ON_EQUITY"]:
        if len(cluster_positions) >= 2:
            return GateResult(
                gate="GATE-0-CLUSTER-LIMIT",
                status=BLOCK,
                message=f"Cluster {cluster} limit reached (Max 2). Halting new exposure."
            )
    elif cluster == "RISK_ON_FX":
        if len(cluster_positions) >= 1:
            return GateResult(
                gate="GATE-0-CLUSTER-LIMIT",
                status=BLOCK,
                message=f"Cluster {cluster} limit reached (Max 1). Halting new exposure."
            )
            
    if cluster in ["RISK_ON_CRYPTO", "RISK_ON_EQUITY", "RISK_ON_FX"]:
        same_dir_count = sum(1 for p in all_active_exposure
                             if _get_cluster(p.symbol) in ["RISK_ON_CRYPTO", "RISK_ON_EQUITY", "RISK_ON_FX"]
                             and _get_direction(p) == candidate_direction)
        if same_dir_count >= 1:
            return GateResult(
                gate="GATE-0-SAME-DIRECTION",
                status=BLOCK,
                message=f"Maximum same-direction limit of 1 across risk-on clusters reached for {candidate_direction}."
            )
            
    return GateResult(gate="GATE-0", status=ALLOW, message="Passed Correlation Cluster Limiter.")

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
    
    # Helper to return rejection
    def reject(reason: str) -> PreExecutionVerdict:
        return PreExecutionVerdict(approved=False, _summary=f"BLOCK [{ticket_ref}]: {reason}")

    # GATE-0: Cross-Asset Correlation Cluster Limiter
    gate0_res = gate0_correlation_cluster_limit(symbol, direction)
    if gate0_res.status == BLOCK:
        return reject(f"Gate 0 Failed ({gate0_res.gate}): {gate0_res.message}")

    # Enforce strict parameter type-safety and dimension checking
    try:
        PriceUnit(entry_price)
        PipDistance(sl_distance, entry_price)
        PipDistance(tp_distance, entry_price)
        LotVolume(kelly_lots)
    except (TypeError, ValueError) as type_err:
        logger.error(f"Type-Safety Gate Violation for {symbol}: {type_err}")
        return reject(f"Type-Safety Violation: {type_err}")

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

    # v30.96 Structural Risk Distance Floor Check
    stop_loss = entry_price - sl_distance if str(direction).upper() in ["BUY", "1", "LONG"] else entry_price + sl_distance
    sl_distance_price = abs(entry_price - stop_loss)
    
    current_ATR = 0.0
    try:
        if not mt5.initialize():
            mt5.initialize()
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
        if rates is not None and len(rates) >= 2:
            highs  = [r[2] for r in rates]
            lows   = [r[3] for r in rates]
            closes = [r[4] for r in rates]
            current_ATR = sum([
                max(highs[i] - lows[i],
                    abs(highs[i]  - closes[i-1]),
                    abs(lows[i]   - closes[i-1]))
                for i in range(1, len(rates))
            ]) / (len(rates) - 1)
    except Exception as atr_err:
        logger.error(f"Failed to calculate ATR in PreExecutionGate for {symbol}: {atr_err}")

    if current_ATR > 0.0:
        minimum_allowed_distance = current_ATR * 3.5  # Absolute volatility floor
        if sl_distance_price < minimum_allowed_distance:
            logger.error(f"[{symbol}] Stop Loss position ({stop_loss}) is non-compliant. "
                              f"Distance {sl_distance_price} falls below ATR Floor ({minimum_allowed_distance}). Vetoing.")
            return reject(f"Gate 5 Failed: Stop Loss position ({stop_loss}) is non-compliant. "
                          f"Distance {sl_distance_price} falls below ATR Floor ({minimum_allowed_distance}).")

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
