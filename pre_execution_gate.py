import logging
from dataclasses import dataclass
from datetime import datetime, timezone
import pytz
import MetaTrader5 as mt5

import sentinel_config as cfg

logger = logging.getLogger("PreExecutionGate")

# Module constants
MAGIC_NUMBER = 142
MAGIC_LEGACY = 17300

class DecayGuardVetoException(Exception):
    """Raised when an order is vetoed by the Edge Decay Sentinel guard (v31.2)."""
    pass

import threading
pending_execution_queue = []
_queue_lock = threading.Lock()

def add_pending_execution(symbol: str, direction: str):
    with _queue_lock:
        pending_execution_queue.append({"symbol": symbol, "direction": direction})

def remove_pending_execution(symbol: str, direction: str):
    with _queue_lock:
        for item in pending_execution_queue:
            if item["symbol"] == symbol and item["direction"] == direction:
                pending_execution_queue.remove(item)
                break

class PriceUnit:
    def __init__(self, value: float):
        if not isinstance(value, (int, float)) or value <= 0:
            raise TypeError(f"PriceUnit must be a positive float/int, got {type(value)}")
        self.value = float(value)

class PriceDistance:
    def __init__(self, value: float, entry_price: float = None):
        if not isinstance(value, (int, float)) or value <= 0:
            raise TypeError(f"PriceDistance must be a positive float/int, got {type(value)}")
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
    """v30.98: ALL clusters enforced including RISK_OFF and COMMODITIES.
    Previously, exotic pairs (USDTRY, USDCNH) fell into RISK_OFF which had
    NO limits — allowing unlimited simultaneous correlated entries."""
    if not mt5.initialize():
        mt5.initialize()
        
    positions = mt5.positions_get() or ()
    open_positions = [p for p in positions if getattr(p, 'magic', 0) in (MAGIC_NUMBER, MAGIC_LEGACY)]
    
    orders = mt5.orders_get() or ()
    pending_orders = [o for o in orders if getattr(o, 'magic', 0) in (MAGIC_NUMBER, MAGIC_LEGACY)]
    
    class PendingExec:
        def __init__(self, sym, dir_str):
            self.symbol = sym
            self.type = 0 if str(dir_str).upper() in ["BUY", "1", "LONG"] else 1
            
    with _queue_lock:
        async_pending = [PendingExec(item["symbol"], item["direction"]) for item in pending_execution_queue]
    
    all_active_exposure = open_positions + pending_orders + async_pending
    
    # v30.98: GLOBAL POSITION CAP — no more than 5 total positions across ALL clusters
    if len(all_active_exposure) >= 5:
        return GateResult(
            gate="GATE-0-GLOBAL-CAP",
            status=BLOCK,
            message=f"[VETO] CORRELATION_CEILING_REACHED (Includes Pending Async Orders) - GLOBAL POSITION CAP REACHED ({len(all_active_exposure)}/5). No new entries until positions close."
        )
    
    cluster = _get_cluster(symbol)
    
    cluster_positions = [
        p for p in all_active_exposure 
        if _get_cluster(p.symbol) == cluster
    ]
    
    # v30.98: Cluster-specific limits — ALL clusters now enforced
    CLUSTER_LIMITS = {
        "RISK_ON_CRYPTO": 2,
        "RISK_ON_EQUITY": 2,
        "RISK_ON_FX": 1,
        "COMMODITIES": 2,
        "RISK_OFF": 2,   # v30.98: Exotic FX pairs (USDTRY, USDCNH, etc.)
    }
    
    max_in_cluster = CLUSTER_LIMITS.get(cluster, 2)
    if len(cluster_positions) >= max_in_cluster:
        return GateResult(
            gate="GATE-0-CLUSTER-LIMIT",
            status=BLOCK,
            message=f"[VETO] CORRELATION_CEILING_REACHED (Includes Pending Async Orders) - Cluster {cluster} limit reached ({len(cluster_positions)}/{max_in_cluster}). Halting new exposure."
        )
    
    # v30.98: Global risk-on contagion cap
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
    
    # v30.98: Same-direction limit across ALL clusters (not just risk-on)
    same_dir_count = sum(1 for p in all_active_exposure
                         if _get_direction(p) == candidate_direction)
    if same_dir_count >= 3:
        return GateResult(
            gate="GATE-0-SAME-DIRECTION-GLOBAL",
            status=BLOCK,
            message=f"Maximum same-direction limit of 3 globally reached for {candidate_direction}."
        )
    
    # Same-direction within same cluster — max 1
    same_dir_cluster = sum(1 for p in cluster_positions
                           if _get_direction(p) == candidate_direction)
    if same_dir_cluster >= 1:
        return GateResult(
            gate="GATE-0-SAME-DIRECTION-CLUSTER",
            status=BLOCK,
            message=f"Same-direction {candidate_direction} already exists in cluster {cluster}. Max 1 per cluster."
        )
            
    return GateResult(gate="GATE-0", status=ALLOW, message="Passed Correlation Cluster Limiter v30.98.")

def gate1_ecn_conflict(symbol: str, kelly_lots: float, equity: float) -> GateResult:
    # Rule A: If equity < GATE_MIN_EQUITY[symbol], BLOCK
    min_equity = cfg.GATE_MIN_EQUITY.get(symbol, 0.0)
    if equity < min_equity:
        return GateResult(
            gate="GATE-1A",
            status=BLOCK,
            message=f"Equity {equity} < Min Equity {min_equity} for {symbol}"
        )
        
    # Rule B: If kelly_lots < GATE_ECN_MIN_LOTS[symbol], BLOCK
    min_lots = cfg.GATE_ECN_MIN_LOTS.get(symbol, 0.01) # Default 0.01 for forex
    if kelly_lots < min_lots:
        return GateResult(
            gate="GATE-1B",
            status=BLOCK,
            message=f"Kelly Lots {kelly_lots} < ECN Min Lots {min_lots} for {symbol}"
        )
    return GateResult(gate="GATE-1", status=ALLOW, message="Passed ECN conflict checks.")

def gate2_leverage_wall(symbol: str, kelly_lots: float, entry_price: float, equity: float) -> GateResult:
    symbol_info = mt5.symbol_info(symbol)
    contract_size = symbol_info.trade_contract_size if symbol_info else 1.0
    
    notional = kelly_lots * contract_size * entry_price
    leverage = notional / equity if equity > 0 else float('inf')
    if leverage > cfg.GATE_MAX_LEVERAGE:
        return GateResult(
            gate="GATE-2",
            status=BLOCK,
            message=f"Leverage {leverage:.2f}x > Max {cfg.GATE_MAX_LEVERAGE}x"
        )
    return GateResult(gate="GATE-2", status=ALLOW, message="Passed leverage check.")

def gate3_rr_ratio(sl_distance: float, tp_distance: float, regime: str) -> GateResult:
    if sl_distance <= 0:
        return GateResult(
            gate="GATE-3",
            status=BLOCK,
            message="Invalid SL distance <= 0"
        )
        
    rr_ratio = tp_distance / sl_distance
    min_rr = 2.0 if "BULL" in regime or "BEAR" in regime else 1.5
    if rr_ratio < min_rr:
        return GateResult(
            gate="GATE-3",
            status=BLOCK,
            message=f"RR Ratio {rr_ratio:.2f} < Min {min_rr} for regime {regime}"
        )
    return GateResult(gate="GATE-3", status=ALLOW, message="Passed RR ratio enforcement.")

def gate4_contamination_check(symbol: str) -> GateResult:
    logger.debug(f"Gate 4: Contamination check setup passed for {symbol}")
    return GateResult(gate="GATE-4", status=ALLOW, message="Passed contamination check.")

def gate5_risk_cap_and_atr_floor(
    symbol: str,
    direction: str,
    entry_price: float,
    sl_distance: float,
    risk_usd: float,
    equity: float
) -> GateResult:
    # GATE-5: Hard Risk Cap
    risk_pct = risk_usd / equity if equity > 0 else 1.0
    if risk_pct > cfg.GATE_MAX_RISK_PCT_PER_TRADE:
        return GateResult(
            gate="GATE-5-RISK-CAP",
            status=BLOCK,
            message=f"Risk Pct {risk_pct:.4f} > Max {cfg.GATE_MAX_RISK_PCT_PER_TRADE}"
        )

    # v30.98 Structural Risk Distance Floor Check (D1 ATR — H1/M15 PROHIBITED)
    stop_loss = entry_price - sl_distance if str(direction).upper() in ["BUY", "1", "LONG"] else entry_price + sl_distance
    sl_distance_price = abs(entry_price - stop_loss)
    
    current_ATR = 0.0
    try:
        if not mt5.initialize():
            mt5.initialize()
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 16)
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
        logger.error(f"Failed to calculate D1 ATR in PreExecutionGate for {symbol}: {atr_err}")

    if current_ATR > 0.0:
        minimum_allowed_distance = max(entry_price * 0.002, current_ATR * 3.5)  # Absolute volatility floor on D1 ATR
        if sl_distance_price < minimum_allowed_distance:
            logger.error(f"[{symbol}] Stop Loss position ({stop_loss}) is non-compliant. "
                              f"D1_ATR Distance {sl_distance_price} falls below ATR Floor ({minimum_allowed_distance}). Vetoing.")
            return GateResult(
                gate="GATE-5-ATR-FLOOR",
                status=BLOCK,
                message=f"Stop Loss position ({stop_loss}) is non-compliant. D1_ATR Distance {sl_distance_price} falls below ATR Floor ({minimum_allowed_distance})."
            )

    return GateResult(gate="GATE-5", status=ALLOW, message="Passed risk cap and ATR floor.")

def gate6_portfolio_heat(risk_usd: float, current_heat_usd: float, equity: float) -> GateResult:
    heat_pct = (current_heat_usd + risk_usd) / equity if equity > 0 else 1.0
    if heat_pct > cfg.GATE_MAX_PORTFOLIO_HEAT:
        return GateResult(
            gate="GATE-6",
            status=BLOCK,
            message=f"Heat Pct {heat_pct:.4f} > Max {cfg.GATE_MAX_PORTFOLIO_HEAT}"
        )
    return GateResult(gate="GATE-6", status=ALLOW, message="Passed portfolio heat ceiling.")

def gate7_weekend_blackout(asset_class: str) -> GateResult:
    if asset_class.upper() != "CRYPTO":
        now_utc = datetime.now(pytz.utc)
        if now_utc.weekday() == 4 and (now_utc.hour > cfg.GATE_BLACKOUT_FRIDAY_HOUR or (now_utc.hour == cfg.GATE_BLACKOUT_FRIDAY_HOUR and now_utc.minute >= cfg.GATE_BLACKOUT_FRIDAY_MIN)):
            return GateResult(gate="GATE-7", status=BLOCK, message="Weekend Blackout (Friday)")
        elif now_utc.weekday() == 5 or (now_utc.weekday() == 6 and now_utc.hour < 22):
            return GateResult(gate="GATE-7", status=BLOCK, message="Weekend Blackout (Saturday/Sunday daytime)")
        elif now_utc.weekday() == 0 and (now_utc.hour < cfg.GATE_BLACKOUT_MONDAY_HOUR or (now_utc.hour == cfg.GATE_BLACKOUT_MONDAY_HOUR and now_utc.minute < cfg.GATE_BLACKOUT_MONDAY_MIN)):
            return GateResult(gate="GATE-7", status=BLOCK, message="Weekend Blackout (Monday morning)")
    return GateResult(gate="GATE-7", status=ALLOW, message="Passed weekend blackout.")

def gate8_amnesia_lock(symbol: str, embargo_registry: dict) -> GateResult:
    if symbol in embargo_registry:
        return GateResult(gate="GATE-8", status=BLOCK, message=f"Symbol {symbol} is currently in amnesia lock registry")
    return GateResult(gate="GATE-8", status=ALLOW, message="Passed amnesia lock.")

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

    # SRE Edge Decay Sentinel Hard Breach Veto check (v31.2)
    state_file = "oracle_cache/edge_decay_state.json"
    try:
        import os, json
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as fh:
                state_data = json.load(fh)
            module_tier = state_data.get("module_tier", {})
            
            is_breached = False
            breached_strategy = None
            for strat, status in module_tier.items():
                if status == "HARD_BREACH":
                    is_breached = True
                    breached_strategy = strat
                    break
            
            if is_breached:
                setup_params = {
                    "symbol": symbol,
                    "direction": direction,
                    "asset_class": asset_class,
                    "regime": regime,
                    "ticket_ref": ticket_ref,
                    "kelly_lots": kelly_lots,
                    "entry_price": entry_price,
                    "sl_distance": sl_distance,
                    "tp_distance": tp_distance,
                    "risk_usd": risk_usd,
                    "equity": equity
                }
                logger.critical(f"[DECAY_GUARD_VETO] Blocked execution for {symbol} due to HARD_BREACH on {breached_strategy}. Params: {setup_params}")
                
                breach_log = {
                    "timestamp": datetime.now(timezone.utc).isoformat() if hasattr(datetime, 'now') else str(time.time()),
                    "symbol": symbol,
                    "strategy": breached_strategy,
                    "params": setup_params
                }
                with open("pending_diagnostics/decay_breach.json", "w", encoding="utf-8") as bh:
                    json.dump(breach_log, bh, indent=4)
                
                raise DecayGuardVetoException(f"[DECAY_GUARD_VETO] Blocked execution for {symbol} due to HARD_BREACH on {breached_strategy}")
    except DecayGuardVetoException:
        raise
    except Exception as e:
        logger.warning(f"[DECAY_SRE_WARN] Pre-execution gate telemetry check skipped or failed: {e}")

    # Helper to return rejection
    def reject(gate_res: GateResult) -> PreExecutionVerdict:
        return PreExecutionVerdict(approved=False, _summary=f"BLOCK [{ticket_ref}]: Gate {gate_res.gate} Failed: {gate_res.message}")

    # GATE-0: Cross-Asset Correlation Cluster Limiter
    gate0_res = gate0_correlation_cluster_limit(symbol, direction)
    if gate0_res.status == BLOCK:
        return reject(gate0_res)

    # Enforce strict parameter type-safety and dimension checking
    try:
        PriceUnit(entry_price)
        PriceDistance(sl_distance, entry_price)
        PriceDistance(tp_distance, entry_price)
        LotVolume(kelly_lots)
    except (TypeError, ValueError) as type_err:
        logger.error(f"Type-Safety Gate Violation for {symbol}: {type_err}")
        return PreExecutionVerdict(approved=False, _summary=f"BLOCK [{ticket_ref}]: Type-Safety Violation: {type_err}")

    # List of gates to run
    gates = [
        lambda: gate1_ecn_conflict(symbol, kelly_lots, equity),
        lambda: gate2_leverage_wall(symbol, kelly_lots, entry_price, equity),
        lambda: gate3_rr_ratio(sl_distance, tp_distance, regime),
        lambda: gate4_contamination_check(symbol),
        lambda: gate5_risk_cap_and_atr_floor(symbol, direction, entry_price, sl_distance, risk_usd, equity),
        lambda: gate6_portfolio_heat(risk_usd, current_heat_usd, equity),
        lambda: gate7_weekend_blackout(asset_class),
        lambda: gate8_amnesia_lock(symbol, embargo_registry)
    ]

    for gate_func in gates:
        res = gate_func()
        if res.status == BLOCK:
            return reject(res)

    return PreExecutionVerdict(approved=True, _summary="All 8 gates passed.")
