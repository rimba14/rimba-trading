import os
import sys
import time
import json
import numpy as np
import MetaTrader5 as mt5

# Add paths to make sure we can import sentinel modules
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import sentinel_config as cfg
import gitagent_utils as utils

# State bridge directories
STATE_DIR = r"C:\Sentinel_Project\data"
if not os.path.exists(STATE_DIR):
    STATE_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\data"

def load_perception_state(worker_type):
    path = os.path.join(STATE_DIR, f"{worker_type}_state.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def main():
    if not mt5.initialize():
        print("[CADES_ERR] MT5 initialization failed.")
        sys.exit(1)

    # 1. Fetch active positions
    positions = mt5.positions_get(magic=cfg.MAGIC_NUMBER) or []
    legacy_positions = mt5.positions_get(magic=143) or [] # Legacy magic
    all_pos = list(positions) + list(legacy_positions)
    
    if not all_pos:
        mt5.shutdown()
        return

    # Load HMM and TimesNet states to determine regimes
    hmm_states = load_perception_state("hmm")
    
    for pos in all_pos:
        symbol = pos.symbol
        digits = mt5.symbol_info(symbol).digits if mt5.symbol_info(symbol) else 5
        is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
        tick = mt5.symbol_info_tick(symbol)
        curr_price = (tick.bid if is_buy else tick.ask) if tick else pos.price_current
        
        # Get HMM/Wasserstein regime for this asset
        hmm_data = hmm_states.get(symbol, {})
        hmm_state = hmm_data.get("metadata", {}).get("hmm_state", "NEUTRAL")
        wasserstein_state = hmm_data.get("metadata", {}).get("wasserstein_state", "LOW-VOL TREND")
        
        # 1. Calculate Safe ATR
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 20)
        if rates is not None and len(rates) > 0:
            highs = np.array([r['high'] for r in rates])
            lows = np.array([r['low'] for r in rates])
            closes = np.array([r['close'] for r in rates])
            tr_list = []
            for i in range(1, len(rates)):
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                tr_list.append(tr)
            macro_atr = float(np.mean(tr_list)) if tr_list else 0.0010
        else:
            macro_atr = 0.0010
            
        # Floor macro_atr at 0.20% of price
        macro_atr = max(macro_atr, 0.0020 * pos.price_open)
        
        # 2. Stop Loss & Take Profit Trailing calculations
        entry = pos.price_open
        is_in_profit = (is_buy and curr_price > entry) or (not is_buy and curr_price < entry)
        
        if not is_in_profit:
            continue # Strict Green Guard
            
        d_current = abs(curr_price - entry)
        
        # If Take Profit/Stop Loss are missing (naked rescue)
        if pos.sl == 0.0 or pos.tp == 0.0:
            raw_sl = entry - (3.5 * macro_atr) if is_buy else entry + (3.5 * macro_atr)
            raw_tp = entry + (5.25 * macro_atr) if is_buy else entry - (5.25 * macro_atr)
            target_sl = round(raw_sl, digits)
            target_tp = round(raw_tp, digits)
            
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": pos.ticket,
                "sl": target_sl,
                "tp": target_tp
            })
            print(f"[CADES_RESCUE] #{pos.ticket} {symbol} SL/TP set: {res.retcode if res else 'Fail'}")
            continue

        # Trail calculation: Geometric condition-scaled parameters
        sl_dist = abs(entry - pos.sl)
        min_tp_dist = 1.5 * sl_dist
        tp_dist = max(5.25 * macro_atr, min_tp_dist)
        
        # In range regimes, take profit is squashed
        if "RANGE" in wasserstein_state or "RANGE" in hmm_state:
            tp_dist *= 0.50 # Squash TP by 50%
            
        new_tp = (entry + tp_dist) if is_buy else (entry - tp_dist)
        target_tp = round(new_tp, digits)
        modify_tp = (abs(pos.tp - target_tp) > 1e-5)
        
        d_target = abs(target_tp - entry)
        d_guard = 0.50 * d_target if ("RANGE" in wasserstein_state or "RANGE" in hmm_state) else 0.80 * d_target
        
        trail_allowed = (d_current >= d_guard)
        target_sl = pos.sl
        modify_sl = False
        
        if trail_allowed:
            # Trailing stop loss moves behind price
            trail_sl = (curr_price - 1.5 * macro_atr) if is_buy else (curr_price + 1.5 * macro_atr)
            # Tighter trail at 85% TP target
            if d_current >= 0.85 * d_target:
                trail_sl = (curr_price - 0.5 * macro_atr) if is_buy else (curr_price + 0.5 * macro_atr)
                
            candidate = round(trail_sl, digits)
            if is_buy and candidate > pos.sl:
                target_sl = candidate
                modify_sl = True
            elif not is_buy and candidate < pos.sl:
                target_sl = candidate
                modify_sl = True
                
        if modify_sl or modify_tp:
            mod_req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": pos.ticket,
                "sl": float(target_sl),
                "tp": float(target_tp)
            }
            res = mt5.order_send(mod_req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[CADES_TRAIL] Updated #{pos.ticket} {symbol}: SL={target_sl:.5f} TP={target_tp:.5f}")
                
    mt5.shutdown()

if __name__ == "__main__":
    main()
