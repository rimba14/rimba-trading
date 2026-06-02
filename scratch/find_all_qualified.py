import sys
import os
import math
import numpy as np
import pandas as pd

sys.path.append(r"C:\Sentinel_Project")
import sentinel_config
import git_arctic
import MetaTrader5 as mt5
import fastapi_sniper as sniper

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    watchlist = sentinel_config.WATCHLIST
    store = git_arctic.get_arctic()
    lib = store['oracle_cache']
    
    qualified = []

    print("=== SCANNING FOR ALL CONSTITUTIONALLY QUALIFIED SIGNALS ===")
    for symbol in watchlist:
        try:
            # 1. Fetch data from oracle cache
            try:
                h_item = lib.read(f"{symbol}_hmm")
                h_data = h_item.data.to_dict('records')[-1]
            except:
                continue

            try:
                k_item = lib.read(f"{symbol}_kronos")
                k_data = k_item.data.to_dict('records')[-1]
            except:
                continue

            try:
                x_item = lib.read(f"{symbol}_xgb")
                x_data = x_item.data.to_dict('records')[-1]
                xgb_p = x_data.get('xgb_prob', 0.50)
            except:
                xgb_p = 0.50

            kronos_p = k_data.get('kronos_prob', 0.50)
            hmm_state = h_data.get('state', 'UNKNOWN')
            hmm_prob = h_data.get('prob', 0.0)
            
            # Determine direction from Kronos
            direction = None
            if kronos_p >= 0.70 and xgb_p >= 0.65:
                direction = "BUY"
            elif kronos_p <= 0.30 and xgb_p <= 0.35:
                direction = "SELL"
                
            if not direction:
                continue

            # Check HMM Regime Alignment
            # Rule 3.3: HMM Regime Probability for predicted direction must be >= 0.60
            # For BUY: HMM State must be BULL or RANGE (if range allows reversed/mean reversion)
            # Wait, the rule is: Reject if HMM Regime Probability < 0.60 or conflict.
            # Usually, direction must match HMM state.
            hmm_aligned = False
            if direction == "BUY" and hmm_state in ["BULL", "RANGE"] and hmm_prob >= 0.60:
                hmm_aligned = True
            elif direction == "SELL" and hmm_state in ["BEAR", "RANGE"] and hmm_prob >= 0.60:
                hmm_aligned = True

            if not hmm_aligned:
                continue

            # If we get here, it's qualified!
            # Fetch live tick and info
            info = mt5.symbol_info(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if not info or not tick:
                continue

            price = tick.ask if direction == "BUY" else tick.bid
            
            # Calculate S/L, T/P and sizing
            p_val = kronos_p
            lot_size = sniper.calculate_kelly_lot(symbol, p_val)
            
            current_atr, _ = sniper.calculate_atr_and_swing(symbol, direction, lookback=20)
            distance_to_fractal_sl = sniper.calculate_fractal_swing(symbol, direction, lookback=20)

            price_based_min = price * 0.0025
            broker_min = info.trade_stops_level * info.point
            current_spread = abs(tick.ask - tick.bid)
            spread_safety = current_spread * 1.5
            sre_safety_floor = max(1.5 * current_atr, spread_safety)

            true_atr = max(current_atr, price_based_min, broker_min, sre_safety_floor)
            sl_dist = max(3.0 * true_atr, distance_to_fractal_sl)

            normalized_p_val = (max(p_val if direction == "BUY" else (1.0 - p_val), 0.60) - 0.60) / 0.40
            tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p_val)
            tp_dist = tp_multiplier * true_atr

            if hmm_state == "RANGE":
                tp_dist = max(tp_dist * 0.45, true_atr * 0.8)

            if direction == "BUY":
                target_sl = price - sl_dist
                target_tp = price + tp_dist
            else:
                target_sl = price + sl_dist
                target_tp = price - tp_dist

            sl = sniper.enforce_stoplevel_and_normalize(symbol, price, target_sl, is_sl=True, is_buy=(direction == "BUY"))
            tp = sniper.enforce_stoplevel_and_normalize(symbol, price, target_tp, is_sl=False, is_buy=(direction == "BUY"))

            # Calculate Risk Reward Ratio
            rr = tp_dist / sl_dist
            
            qualified.append({
                "symbol": symbol,
                "direction": direction,
                "hmm_state": hmm_state,
                "hmm_prob": hmm_prob,
                "kronos": kronos_p,
                "xgb": xgb_p,
                "price": price,
                "sl": sl,
                "tp": tp,
                "lot": lot_size,
                "rr": rr
            })
        except Exception as e:
            # print(f"Error scanning {symbol}: {e}")
            pass

    print(f"\nFound {len(qualified)} fully qualified entries:")
    for q in qualified:
        print(f"\nAsset: {q['symbol']} ({q['direction']})")
        print(f"HMM Regime: {q['hmm_state']} ({q['hmm_prob']:.1%})")
        print(f"Kronos: {q['kronos']:.3f} | XGBoost: {q['xgb']:.3f}")
        print(f"Current Price: {q['price']:.5f}")
        print(f"Stop Loss (S/L): {q['sl']:.5f}")
        print(f"Take Profit (T/P): {q['tp']:.5f}")
        print(f"Risk Reward Ratio (R:R): {q['rr']:.2f}")
        print(f"Lot Sizing: {q['lot']:.4f}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
