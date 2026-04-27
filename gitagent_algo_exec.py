import MetaTrader5 as mt5
import time
import random
import gitagent_execute_sor as sor
import numpy as np
import gitagent_utils as utils

def execute_iceberg(symbol, order_type, total_volume, sl_p, tp_p, num_clips=5, window_sec=10):
    """
    Iceberg Order: Splits a large order into random smaller clips executed over a time window.
    Reduces market impact and hides true size from the book.
    """
    print(f"[ALGO] Executing ICEBERG for {symbol} | Total: {total_volume} | Clips: {num_clips}")
    
    # Fetch symbol info for volume constraints
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"[ALGO_ERR] Failed to get symbol info for {symbol}")
        # Final fallback: direct normalized order
        norm_vol = utils.normalize_volume(symbol, total_volume)
        return sor.execute_standard_order(symbol, order_type, norm_vol, sl_p, tp_p, "Iceberg_Fallback")
    
    v_min = info.volume_min
    
    # Base volume per clip
    base_clip_raw = total_volume / num_clips
    base_clip = utils.normalize_volume(symbol, base_clip_raw)
    
    # If base clip is below min, reduce number of clips
    if base_clip <= v_min:
        base_clip = v_min
        num_clips = int(total_volume / v_min)
        if num_clips < 1: num_clips = 1
        
    print(f"[ALGO] Adjusted ICEBERG: {num_clips} clips of ~{base_clip}")
    
    executed_vol = 0.0
    results = []
    
    # Position Limit Gate (v11.5)
    from gitagent_utils import MAX_TOTAL_POSITIONS

    for i in range(num_clips):
        # 1. Symbol Lock (Phase 87: Iceberg Duplicate Prevention)
        if mt5.positions_get(symbol=symbol):
            print(f"[ALGO] ICEBERG HALTED: Symbol {symbol} already active. Blocking redundant clips.")
            break

        # 2. Mandatory Risk Check: Are we already over-leveraged?
        curr_pos = mt5.positions_get()
        if curr_pos and len(curr_pos) >= MAX_TOTAL_POSITIONS:
            print(f"[ALGO] ICEBERG HALTED: Position limit reached ({len(curr_pos)} >= {MAX_TOTAL_POSITIONS})")
            break

        # Calculate random fuzz for this clip (+/- 20%), except the last one
        if i == num_clips - 1:
            clip_vol = utils.normalize_volume(symbol, total_volume - executed_vol)
        else:
            fuzz = random.uniform(0.8, 1.2)
            clip_vol = utils.normalize_volume(symbol, base_clip * fuzz)
            
        if clip_vol < v_min: clip_vol = v_min
        if executed_vol + clip_vol > total_volume:
            clip_vol = utils.normalize_volume(symbol, total_volume - executed_vol)
            
        if clip_vol <= 0: break
        
        # Execute clip
        comment = f"Iceberg_Clip_{i+1}"
        from gitagent_action_layer import get_action_layer
        action_layer = get_action_layer()
        res = action_layer.execute_smart_trade(symbol, order_type, clip_vol, sl_p, tp_p, comment=comment)
        if res:
            # result might be a list (from synth SOR) or a single MockResult/Order
            main_res = res[0] if isinstance(res, list) and len(res) > 0 else res
            results.append(main_res)
            executed_vol += clip_vol
            
        # Random sleep interval
        if i < num_clips - 1:
            sleep_t = random.uniform(0, window_sec / (num_clips - 1))
            time.sleep(sleep_t)
            
    print(f"[ALGO] ICEBERG Complete. Executed {executed_vol}/{total_volume}")
    return results[0] if results else None

def execute_twap(symbol, order_type, total_volume, sl_p, tp_p, duration_sec=60, clips=6):
    """
    TWAP: Time-Weighted Average Price.
    """
    print(f"[ALGO] Executing TWAP for {symbol} | Total: {total_volume} | Duration: {duration_sec}s")
    
    executed_vol = 0.0
    results = []
    interval = duration_sec / clips
    
    for i in range(clips):
        if i == clips - 1:
            current_clip = utils.normalize_volume(symbol, total_volume - executed_vol)
        else:
            current_clip = utils.normalize_volume(symbol, total_volume / clips)
            
        if current_clip <= 0: continue
        
        from gitagent_action_layer import get_action_layer
        action_layer = get_action_layer()
        res = action_layer.execute_smart_trade(symbol, order_type, current_clip, sl_p, tp_p, comment=f"TWAP_Clip_{i+1}")
        if res:
            main_res = res[0] if isinstance(res, list) and len(res) > 0 else res
            results.append(main_res)
            executed_vol += current_clip
            
        if i < clips - 1:
            time.sleep(interval)
            
    return results[0] if results else None

def route_algorithmic_order(symbol, order_type, volume, sl_p, tp_p, **kwargs):
    """
    Intelligent Algo Router.
    """
    if not utils.is_market_open(symbol):
        print(f"[ALGO] Skipping {symbol}: Market appears closed or inactive.")
        return None
        
    # v12.6 Liquidity Gate: Block high-spread noise
    current_atr = kwargs.get('atr', 0)
    if not utils.is_liquidity_safe(symbol, current_atr):
        return None

    norm_vol = utils.normalize_volume(symbol, volume)
    if norm_vol <= 0: return None
    
    from gitagent_action_layer import get_action_layer
    action_layer = get_action_layer()
    
    if norm_vol >= 0.5:
        return execute_iceberg(symbol, order_type, norm_vol, sl_p, tp_p, num_clips=5, window_sec=15)
    else:
        return action_layer.execute_smart_trade(symbol, order_type, norm_vol, sl_p, tp_p)

if __name__ == "__main__":
    if mt5.initialize():
        print("ALGO EXEC ENGINE READY")
        mt5.shutdown()
