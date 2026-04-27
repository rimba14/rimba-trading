import MetaTrader5 as mt5
import os
import json
import time
import logging
import sys
from datetime import datetime

# Inject project path
sys.path.append(r"C:\Sentinel_Project")
import git_arctic
import gitagent_utils as utils

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [EXECUTOR_MCP] %(message)s')

# Constants
MAGIC_NUMBER = 142
KELLY_FRACTION = 0.25  # Quarter-Kelly
DEVIATION = 20

def get_asset_multiplier(symbol):
    """Returns ATR multiplier based on asset class. Queries ArcticDB for optimized values."""
    regime = utils.get_symbol_regime(symbol)
    
    # Directive 1 (The Sisyphus Cure): Query ArcticDB for Dynamic Multipliers
    try:
        store = git_arctic.get_arctic()
        if 'global_hyperparameters' in store.list_libraries():
            lib_hp = store['global_hyperparameters']
            hp_data = lib_hp.read(f"atr_mult_{regime}")
            if hp_data is not None and not hp_data.data.empty:
                optimized_val = float(hp_data.data.iloc[-1]['atr_multiplier'])
                logging.info(f"[ARCTIC] Using Dynamic ATR Multiplier for {regime}: {optimized_val}x")
                return optimized_val
    except Exception as e:
        logging.warning(f"Feature Store query failed: {e}. Using Constitutional defaults.")

    # Constitutional Defaults (Fallback)
    if regime == "FOREX_USD" or regime == "FOREX_CROSS":
        return 6.0
    elif regime in ["INDEX", "COMMODITY", "CRYPTO"]:
        return 4.0
    elif regime == "EQUITY":
        return 3.0
    return 4.0 # Default

def execute_trade(symbol, conviction, hmm_regime):
    """
    Absolute authority for trade execution.
    conviction: 0.0 to 1.0 (0.5 is neutral)
    """
    if not mt5.initialize():
        logging.error("MT5 Initialization failed.")
        return {"status": "error", "message": "MT5_INIT_FAILED"}

    try:
        # 1. Fetch Symbol Info
        info = mt5.symbol_info(symbol)
        if not info:
            return {"status": "error", "message": f"SYMBOL_NOT_FOUND: {symbol}"}
        
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                return {"status": "error", "message": f"SYMBOL_SELECT_FAILED: {symbol}"}

        # 2. Fetch ATR and XGBoost baseline from cache
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        
        k_item = lib.read(f"{symbol}_kronos")
        if k_item is None:
            return {"status": "error", "message": "MISSING_CACHE_DATA"}
        
        k_data = k_item.data.iloc[-1]
        base_atr = float(k_data.get('base_atr', 0.0))
        if base_atr <= 0:
            # Fallback to manual calculation if cache is empty
            from gitagent_sigproc import get_m15_dataframe
            df = get_m15_dataframe(symbol, 100)
            base_atr = utils.calculate_atr(df)

        # 3. Kelly Sizing (0.25 Quarter-Kelly)
        p = conviction if conviction > 0.5 else (1.0 - conviction)
        q = 1.0 - p
        b = 1.5 # Win/Loss Ratio Proxy
        f_star_raw = p - (q / b)
        f_star_adj = max(0, f_star_raw * KELLY_FRACTION)
        
        # Hard Risk Cap: 2%
        f_final = min(f_star_adj, 0.02)
        
        acc = mt5.account_info()
        if not acc:
            return {"status": "error", "message": "ACCOUNT_INFO_FAILED"}
        
        risk_usd = acc.equity * f_final
        if risk_usd <= 0:
            return {"status": "error", "message": "KELLY_ZERO_OR_NEGATIVE", "f_star": f_star_adj}

        # 4. SL Calculation (Asset-Class Multiplier)
        # Directive: Physical Stop Loss (v16.8)
        # We transmit a hard SL price directly to the broker on entry.
        # This SL is based on the VectorBT-optimized Asset-Class ATR multiplier.
        standard_multiplier = get_asset_multiplier(symbol)
        sl_distance = base_atr * standard_multiplier
        
        # Ensure SL is at least 2x spread
        tick = mt5.symbol_info_tick(symbol)
        spread = (tick.ask - tick.bid) if tick else 0.0
        sl_distance = max(sl_distance, spread * 2.0)
        
        # Stretch to legal boundary (trade_stops_level)
        stops_level = info.trade_stops_level * info.point
        sl_distance = max(sl_distance, stops_level + info.point)

        # 5. Lot Size Calculation (based on full risk across grid)
        # We split the risk among 5 orders
        risk_per_order = risk_usd / 5.0
        
        tick_val = info.trade_tick_value
        tick_size = info.trade_tick_size
        point_val = tick_val / (tick_size / info.point)
        
        # Total Lot calculation
        total_vol = risk_usd / (sl_distance / info.point * point_val + 1e-12)
        vol_per_order = utils.normalize_volume(symbol, total_vol / 5.0)
        
        if vol_per_order < info.volume_min:
            return {"status": "error", "message": "VOLUME_TOO_LOW", "vol": vol_per_order}

        # 6. Grid Execution (1 Market, 4 Limits)
        direction = mt5.ORDER_TYPE_BUY if conviction > 0.5 else mt5.ORDER_TYPE_SELL
        results = []
        
        # Market Order
        price = tick.ask if direction == mt5.ORDER_TYPE_BUY else tick.bid
        sl = price - sl_distance if direction == mt5.ORDER_TYPE_BUY else price + sl_distance
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol_per_order,
            "type": direction,
            "price": price,
            "sl": sl,
            "deviation": DEVIATION,
            "magic": MAGIC_NUMBER,
            "comment": f"Sentinel_v15_Mkt_{hmm_regime}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        results.append({"type": "market", "retcode": res.retcode, "deal": res.deal})
        
        # 4 Limit Orders at 0.5x ATR pullbacks
        for i in range(1, 5):
            pullback = i * 0.5 * base_atr
            limit_price = price - pullback if direction == mt5.ORDER_TYPE_BUY else price + pullback
            limit_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_SELL_LIMIT
            
            # Independent SL for each limit
            limit_sl = limit_price - sl_distance if direction == mt5.ORDER_TYPE_BUY else limit_price + sl_distance
            
            limit_request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": vol_per_order,
                "type": limit_type,
                "price": limit_price,
                "sl": limit_sl,
                "magic": MAGIC_NUMBER,
                "comment": f"Sentinel_v15_Lim{i}_{hmm_regime}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            res_lim = mt5.order_send(limit_request)
            results.append({"type": f"limit_{i}", "retcode": res_lim.retcode, "order": res_lim.order})
            
        return {
            "status": "success",
            "symbol": symbol,
            "direction": "BUY" if direction == mt5.ORDER_TYPE_BUY else "SELL",
            "risk_usd": round(risk_usd, 2),
            "vol_per_order": vol_per_order,
            "sl_distance": round(sl_distance, 5),
            "grid_results": results
        }

    except Exception as e:
        logging.error(f"Execution Error: {e}")
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

if __name__ == "__main__":
    # Test script
    if len(sys.argv) > 3:
        sym = sys.argv[1]
        conv = float(sys.argv[2])
        reg = sys.argv[3]
        print(json.dumps(execute_trade(sym, conv, reg), indent=2))
    else:
        print("Usage: python trade_executor_mcp.py <symbol> <conviction> <hmm_regime>")
