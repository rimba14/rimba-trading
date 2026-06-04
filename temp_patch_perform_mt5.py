import re

file_path = r'C:\Sentinel_Project\fastapi_sniper.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''
        # Directive 3: TimesFM Coherence Protection
        tfm_dist, tfm_valid = get_timesfm_sl_distance(symbol, direction, price, current_atr)
        calculated_sl_dist = tfm_dist
        
        broker_minimum_sl = info.trade_stops_level * info.point if info else 0.0001
        final_sl_dist = max(calculated_sl_dist, broker_minimum_sl)
        
        logger.info(f"[{symbol}] CADES SL Validation: ATR={current_atr:.5f} | TimesFM_Valid={tfm_valid} | FinalSL={final_sl_dist:.5f}")
        
        sl_price = price - final_sl_dist if direction == "BUY" else price + final_sl_dist
        sl_price = round(sl_price, digits)

        # Directive 1: Ensure Conviction score (P) is correctly extracted. Default to 0.80 if missing.
        conv_val = conviction if conviction is not None and conviction > 0 else 0.80
        # If conviction is already absolute directional confidence, use directly, otherwise normalize
        p_entry = conv_val if direction == "BUY" else (1.0 - conv_val)
        if p_entry < 0.5:
            p_entry = abs(conv_val - 0.5) + 0.5
        p_entry = max(p_entry, 0.60)
        
        # Directive 1: Implement Logarithmic TP Squashing (SRE Optimization)
        # Linear: tp_dist = current_atr * (2.0 + 4.0 * ((p_entry - 0.60) / 0.40))
        normalized_p = (p_entry - 0.60) / 0.40
        tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
        tp_dist = current_atr * tp_multiplier
        
        # --- NEW LOGIC: Recalculate Lot Size based on Final SL & Enforce TP Floor ---
        # Sizing Recalculation
        acc = mt5.account_info()
        sl_dist_points = final_sl_dist / (info.point + 1e-12)
        point_val = info.trade_tick_value / (info.trade_tick_size / info.point)
        max_dollar_risk = acc.balance * 0.02
        atr_raw_vol = max_dollar_risk / (sl_dist_points * point_val + 1e-12)
        atr_adjusted_lot = math.floor(atr_raw_vol / info.volume_step) * info.volume_step
        lot = min(lot, atr_adjusted_lot)
        if lot <= 0.0:
            lot = info.volume_min
            logger.warning(f"[{symbol}] Post-Floor Lot Sizing Warning: Recalculated lot <= 0, defaulting to min {lot}")

        # TP Floor Logic
        SYMMETRIC_TP_RATIO = 1.5
        symmetric_tp_floor = final_sl_dist * SYMMETRIC_TP_RATIO
        if tp_dist < symmetric_tp_floor:
            logger.info(f"[{symbol}] [WALL8_SYMMETRIC_TP] Override engaged: TP locked to {SYMMETRIC_TP_RATIO}x SL.")
            tp_dist = symmetric_tp_floor
        # --------------------------------------------------------------------------

        # Directional Math: BUY = entry + tp_dist, SELL = entry - tp_dist
        tp_price = price + tp_dist if direction == "BUY" else price - tp_dist
        tp_price = round(tp_price, digits)
        
        logger.info(f"[{symbol}] CADES TP Scaled: P={p_entry:.4f} -> TP Dist={tp_dist/current_atr:.2f}x ATR")
'''

pattern = re.compile(r'        # Directive 3: TimesFM Coherence Protection.*?logger\.info\(f"\[\{symbol\}\] CADES TP Scaled: P=\{p_entry:\.4f\} -> TP Dist=\{tp_dist/current_atr:\.2f\}x ATR"\)', re.DOTALL)
new_content = pattern.sub(replacement.strip(), content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Patch applied to perform_mt5_trade")
