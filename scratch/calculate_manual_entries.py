import sys
import os
import math
import pandas as pd
import MetaTrader5 as mt5

project_dir = r"C:\Sentinel_Project"
sys.path.append(project_dir)

import fastapi_sniper
import git_arctic
from sentinel_config import WATCHLIST

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    ac = git_arctic.get_arctic()
    if 'oracle_cache' not in ac.list_libraries():
        print("[ERROR] 'oracle_cache' library not found in ArcticDB.")
        return

    lib = ac['oracle_cache']
    symbols = lib.list_symbols()
    
    candidates = []
    high_vol_assets = {"NAS100", "US30", "SPX500", "SP500", "GER40", "NAS100.r", "XAUUSD", "XAGUSD", "GOLD", "SILVER"}
    
    for symbol in WATCHLIST:
        meta_key = f"{symbol}_meta"
        if meta_key not in symbols:
            continue
            
        try:
            df = lib.read(meta_key).data
            if df.empty:
                continue
                
            last_row = df.iloc[-1]
            conviction = float(last_row.get("meta_conviction", 0.50))
            hmm_state = str(last_row.get("hmm_state", "RANGE"))
            strategy_type = str(last_row.get("strategy_type", "MOMENTUM"))
            
            # Absolute conviction
            norm_p = abs(conviction - 0.5) + 0.5
            direction = "BUY" if conviction >= 0.50 else "SELL"
            
            # Check for conflict
            conflict = False
            if hmm_state == "BEAR" and direction == "BUY":
                conflict = True
            elif hmm_state == "BULL" and direction == "SELL":
                conflict = True
                
            # Reconstruct the dynamic gate
            base_gate = 0.72 if symbol.upper() in high_vol_assets else 0.68
            
            candidates.append({
                "symbol": symbol,
                "direction": direction,
                "conviction": conviction,
                "norm_p": norm_p,
                "hmm_state": hmm_state,
                "strategy_type": strategy_type,
                "gate": base_gate,
                "conflict": conflict
            })
        except Exception:
            continue
            
    # Filter candidates with NO regime conflict
    valid_candidates = [c for c in candidates if not c["conflict"]]
    # Sort by norm_p descending
    valid_candidates.sort(key=lambda x: x["norm_p"], reverse=True)
    
    print("=========================================================================")
    print("                TOP VALID CANDIDATES (NO REGIME CONFLICT)                ")
    print("=========================================================================")
    for idx, c in enumerate(valid_candidates[:5]):
        print(f"[{idx+1}] {c['symbol']} ({c['direction']}) | Strategy: {c['strategy_type']} | P: {c['conviction']:.4f} | Norm P: {c['norm_p']:.4f} vs Gate: {c['gate']:.2f} | HMM: {c['hmm_state']}")
        
    print("\n=========================================================================")
    print("              CALCULATING PRECISE PARAMS FOR TOP 2 TRADES                ")
    print("=========================================================================")
    
    for idx, c in enumerate(valid_candidates[:2]):
        symbol = c["symbol"]
        direction = c["direction"]
        conv = c["conviction"]
        
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        acc = mt5.account_info()
        
        if not info or not tick or not acc:
            print(f"Failed to load details for {symbol}")
            continue
            
        digits = info.digits
        entry_price = tick.ask if direction == "BUY" else tick.bid
        
        # SL calculation
        current_atr, _ = fastapi_sniper.calculate_atr_and_swing(symbol, direction, lookback=20)
        distance_to_fractal_sl = fastapi_sniper.calculate_fractal_swing(symbol, direction, lookback=20)
        sl_dist_price = max(3.0 * current_atr, distance_to_fractal_sl)
        broker_minimum_sl = info.trade_stops_level * info.point if info else 0.0001
        final_sl_dist = max(sl_dist_price, broker_minimum_sl)
        
        sl_price = entry_price - final_sl_dist if direction == "BUY" else entry_price + final_sl_dist
        sl_price = round(sl_price, digits)
        
        # Sizing
        lot_size = fastapi_sniper.calculate_kelly_lot(symbol, conv)
        
        # TP calculation
        p_entry = conv if direction == "BUY" else (1.0 - conv)
        if p_entry < 0.5:
            p_entry = abs(conv - 0.5) + 0.5
        p_entry = max(p_entry, 0.60)
        
        normalized_p = (p_entry - 0.60) / 0.40
        tp_multiplier = 2.0 + 2.0 * math.log10(1 + 9 * normalized_p)
        tp_dist = current_atr * tp_multiplier
        
        tp_price = entry_price + tp_dist if direction == "BUY" else entry_price - tp_dist
        tp_price = round(tp_price, digits)
        
        print(f"\nRANK #{idx+1}: {symbol} {direction} (P = {conv:.4f}, Norm P = {c['norm_p']:.4f})")
        print(f"  Entry Price (Current Bid/Ask): {entry_price}")
        print(f"  Calculated Sizing (Lot Size):  {lot_size:.2f} lots")
        print(f"  Calculated Stop Loss (SL):     {sl_price}")
        print(f"  Calculated Take Profit (TP):   {tp_price}")
        print(f"  Details: ATR={current_atr:.5f} | FractalSL={distance_to_fractal_sl:.5f} | TPMultiplier={tp_multiplier:.3f}x")

if __name__ == "__main__":
    main()
