import sys
import os
import math
import MetaTrader5 as mt5

project_dir = r"C:\Sentinel_Project"
sys.path.append(project_dir)

import fastapi_sniper

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    symbol = "US2000"
    direction = "SELL"
    
    # Try different conviction scores (P) for SELL (where P < 0.5)
    # P = 0.32 (Norm P = 0.68)
    # P = 0.28 (Norm P = 0.72)
    # P = 0.20 (Norm P = 0.80)
    convictions = [0.32, 0.28, 0.20]
    
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    acc = mt5.account_info()
    
    if not info:
        print(f"Symbol info for {symbol} not found.")
        return
    if not tick:
        print(f"No tick data for {symbol}.")
        return
    if not acc:
        print("Failed to get account info.")
        return

    print("=========================================================================")
    print(f"         US2000 SELL CALCULATION AUDIT (v28.29 FORMULAS)                 ")
    print("=========================================================================")
    print(f"MT5 Account Balance: ${acc.balance:,.2f}")
    print(f"MT5 Account Equity:  ${acc.equity:,.2f}")
    print(f"US2000 Ask Price:    {tick.ask}")
    print(f"US2000 Bid Price:    {tick.bid}")
    print(f"US2000 Point Size:   {info.point}")
    print(f"US2000 Volume Min:   {info.volume_min}")
    print(f"US2000 Volume Max:   {info.volume_max}")
    print(f"US2000 Volume Step:  {info.volume_step}")
    
    current_atr, _ = fastapi_sniper.calculate_atr_and_swing(symbol, direction, lookback=20)
    distance_to_fractal_sl = fastapi_sniper.calculate_fractal_swing(symbol, direction, lookback=20)
    sl_dist_price = max(3.0 * current_atr, distance_to_fractal_sl)
    broker_minimum_sl = info.trade_stops_level * info.point if info else 0.0001
    final_sl_dist = max(sl_dist_price, broker_minimum_sl)
    
    entry_price = tick.bid # SELL entry at bid price
    sl_price = entry_price + final_sl_dist
    digits = info.digits
    sl_price = round(sl_price, digits)
    
    print(f"\n--- STOP LOSS (SL) PARAMETERS ---")
    print(f"20-Period ATR:                   {current_atr:.5f}")
    print(f"Distance to 20-Period Fractal SL: {distance_to_fractal_sl:.5f}")
    print(f"Calculated SL Distance:          {final_sl_dist:.5f}")
    print(f"Target SL Price (SELL Entry):     {sl_price:.2f}")

    print(f"\n--- SCENARIO ANALYSIS BY CONVICTION ---")
    for conv in convictions:
        norm_p = abs(conv - 0.5) + 0.5
        # Sizing calculation
        lot_size = fastapi_sniper.calculate_kelly_lot(symbol, conv)
        
        # TP calculation
        p_entry = conv if direction == "BUY" else (1.0 - conv)
        if p_entry < 0.5:
            p_entry = abs(conv - 0.5) + 0.5
        p_entry = max(p_entry, 0.60)
        
        normalized_p = (p_entry - 0.60) / 0.40
        tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
        tp_dist = current_atr * tp_multiplier
        tp_price = entry_price - tp_dist
        tp_price = round(tp_price, digits)
        
        print(f"\nConviction P = {conv:.2f} (Absolute/Norm P = {norm_p:.2f})")
        print(f"  Calculated Sizing (Lot Size):  {lot_size:.2f} lots")
        print(f"  TP Multiplier:                 {tp_multiplier:.4f}x ATR")
        print(f"  TP Distance:                   {tp_dist:.5f}")
        print(f"  Target TP Price (SELL Entry):   {tp_price:.2f}")
        print(f"  Risk-to-Reward Ratio (R):      {tp_dist / final_sl_dist:.2f}R")

if __name__ == "__main__":
    main()
