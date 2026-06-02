import sys
import os
import math
import numpy as np

sys.path.append(r"C:\Sentinel_Project")
import MetaTrader5 as mt5
import fastapi_sniper as sniper

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    # Targets from active meta signals
    candidates = [
        {"symbol": "USDCAD", "direction": "SELL", "conviction": 0.3481, "hmm_state": "BEAR"},
        {"symbol": "GBPJPY", "direction": "SELL", "conviction": 0.4327, "hmm_state": "BEAR"},
        {"symbol": "CHFJPY", "direction": "BUY", "conviction": 0.5822, "hmm_state": "BULL"},
        {"symbol": "AUDUSD", "direction": "BUY", "conviction": 0.5682, "hmm_state": "BULL"}
    ]

    print("=== LIVE MANUAL ENTRY CALCULATIONS (NEW CANDIDATES) ===")
    for c in candidates:
        symbol = c["symbol"]
        direction = c["direction"]
        conviction = c["conviction"]
        hmm_state = c["hmm_state"]

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not info or not tick:
            print(f"[WARN] {symbol} info/tick not available. Skipping.")
            continue

        # Get current price
        price = tick.bid if direction == "SELL" else tick.ask

        # 1. calculate lot size
        lot_size = sniper.calculate_kelly_lot(symbol, conviction)

        # 2. calculate SL and TP
        current_atr, _ = sniper.calculate_atr_and_swing(symbol, direction, lookback=20)
        distance_to_fractal_sl = sniper.calculate_fractal_swing(symbol, direction, lookback=20)

        price_based_min = price * 0.0025
        broker_min = info.trade_stops_level * info.point
        current_spread = abs(tick.ask - tick.bid)
        spread_safety = current_spread * 1.5
        sre_safety_floor = max(1.5 * current_atr, spread_safety)

        true_atr = max(current_atr, price_based_min, broker_min, sre_safety_floor)
        sl_dist = max(3.0 * true_atr, distance_to_fractal_sl)

        p_val = conviction
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

        print(f"\nAsset: {symbol}")
        print(f"Direction: {direction}")
        print(f"HMM State: {hmm_state}")
        print(f"Norm P: {abs(conviction - 0.5) + 0.5:.4f}")
        print(f"Current Price: {price:.5f}")
        print(f"Calculated Lot Sizing: {lot_size:.2f}")
        print(f"Precise Stop Loss (S/L): {sl:.5f}")
        print(f"Precise Take Profit (T/P): {tp:.5f}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
