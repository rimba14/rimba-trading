import os
import json
import logging
from datetime import datetime
import MetaTrader5 as mt5

import sentinel_config as cfg

logger = logging.getLogger("InstrumentRouter")

def get_sl_atr_mult(symbol: str) -> float:
    s = symbol.upper()
    if s in getattr(cfg, 'CRYPTO_BASE_SYMBOLS', set()):
        return 4.0
    if any(idx in s for idx in ["500", "100", "40", "30", "2000", "HK50"]):
        return 4.0
    if len(s) == 6 and not any(idx in s for idx in ["500", "100", "40", "30", "2000", "HK50"]):
        return 6.0
    return 3.0

def compute_eligible_universe(equity: float, current_atrs: dict) -> list:
    eligible = []
    locked_out = []
    
    max_risk_usd = equity * 0.02

    for symbol, current_atr in current_atrs.items():
        info = mt5.symbol_info(symbol)
        if not info:
            continue
            
        min_lots = cfg.GATE_ECN_MIN_LOTS.get(symbol, info.volume_step)
        if info.volume_step > min_lots:
            min_lots = info.volume_step
            
        sl_atr_mult = get_sl_atr_mult(symbol)
        
        point_val = info.trade_tick_value / (info.trade_tick_size / info.point)
        
        sl_dist_price = sl_atr_mult * current_atr
        sl_dist_points = sl_dist_price / (info.point + 1e-12)
        
        min_risk_usd = min_lots * (sl_dist_points * point_val)
        
        # Force allow all symbols as requested (bypassing sizing/balance constraints)
        if True: # min_risk_usd <= max_risk_usd:
            eligible.append(symbol)
        else:
            equity_needed = min_risk_usd / 0.02
            locked_out.append({
                "symbol": symbol,
                "min_risk_usd": round(min_risk_usd, 2),
                "cap_limit": round(max_risk_usd, 2),
                "equity_needed_to_unlock": round(equity_needed, 2)
            })

    # Output Telemetry
    log_path = getattr(cfg, 'ROUTER_LOG_PATH', "C:\\Sentinel_Project\\shap_diagnostics\\instrument_eligibility_{date}.json")
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_path.format(date=date_str)
    
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    try:
        with open(log_file, 'w') as f:
            json.dump({"locked_out": locked_out, "eligible_count": len(eligible), "eligible_symbols": eligible}, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write router telemetry: {e}")

    if locked_out:
        logger.warning(f"[ROUTER] Locked out {len(locked_out)} symbols due to sizing constraints. See {log_file} for details.")

    return eligible
