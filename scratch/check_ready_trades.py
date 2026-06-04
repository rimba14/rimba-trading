import sys
import os
import time
import pandas as pd
from datetime import datetime, timezone

project_dir = r"C:\Sentinel_Project"
sys.path.append(project_dir)

import git_arctic
from sentinel_config import WATCHLIST

def check_ready_trades():
    print("=========================================================================")
    print("              ADAPTIVE SENTINEL TRADES READINESS REPORT                  ")
    print("=========================================================================")
    
    ac = git_arctic.get_arctic()
    if 'oracle_cache' not in ac.list_libraries():
        print("[ERROR] 'oracle_cache' library not found in ArcticDB.")
        return

    lib = ac['oracle_cache']
    symbols = lib.list_symbols()
    
    ready_trades = []
    close_trades = []
    other_trades = []
    
    current_time = time.time()
    
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
            
            # Extract fields
            conviction = float(last_row.get("meta_conviction", 0.50))
            hmm_state = str(last_row.get("hmm_state", "RANGE"))
            strategy_type = str(last_row.get("strategy_type", "MOMENTUM"))
            primary_dir = int(last_row.get("primary_dir", 0))
            timestamp = float(last_row.get("timestamp", 0.0))
            
            # Calculate norm_p (absolute conviction)
            norm_p = abs(conviction - 0.5) + 0.5
            
            # Determine direction
            direction = "BUY" if conviction >= 0.50 else "SELL"
            
            # Reconstruct the dynamic gate
            base_gate = 0.72 if symbol.upper() in high_vol_assets else 0.68
            # In sentinel_slow_loop, dynamic gate starts from base_gate and can be relaxed:
            # - Regime-Awareness Patch: if regime confidence < 0.55, relax by 0.05
            # - Let's read the last row values.
            # (To be safe, we'll display both the norm_p and the default gates)
            
            # Wait, let's look at is_graveyard or is_legend
            is_graveyard = last_row.get("is_graveyard", False)
            is_legend = last_row.get("is_legend", False)
            
            staleness = current_time - timestamp
            
            # Skip stale data (> 10 minutes)
            if staleness > 600:
                continue
                
            # Distance to gate
            gate_threshold = base_gate
            # We relax the gate for low regime confidence
            # Let's check: in sentinel_slow_loop:
            # - if regime_prob < 0.55: current_gate = max(current_gate - 0.05, 0.60)
            # Let's list the distance
            dist = gate_threshold - norm_p
            
            record = {
                "symbol": symbol,
                "conviction": conviction,
                "norm_p": norm_p,
                "direction": direction,
                "hmm_state": hmm_state,
                "strategy_type": strategy_type,
                "gate_threshold": gate_threshold,
                "dist": dist,
                "staleness": staleness,
                "is_graveyard": is_graveyard,
                "is_legend": is_legend
            }
            
            if norm_p >= gate_threshold:
                ready_trades.append(record)
            elif dist <= 0.06:
                close_trades.append(record)
            else:
                other_trades.append(record)
                
        except Exception as e:
            continue
            
    print("\n[1] READY TRADES (Absolute Conviction >= Gate Threshold)")
    print(f"{'Symbol':<10} | {'Dir':<4} | {'Strategy':<15} | {'Conviction':<10} | {'Norm P':<7} | {'Gate':<6} | {'HMM State':<10} | {'Stale (s)':<9}")
    print("-" * 90)
    ready_trades.sort(key=lambda x: x['norm_p'], reverse=True)
    for r in ready_trades:
        print(f"{r['symbol']:<10} | {r['direction']:<4} | {r['strategy_type']:<15} | {r['conviction']:.4f}     | {r['norm_p']:.4f}  | {r['gate_threshold']:.2f} | {r['hmm_state']:<10} | {r['staleness']:.1f}")
        
    print("\n[2] CLOSE TO FIRING (Within 6% of Gate Threshold)")
    print(f"{'Symbol':<10} | {'Dir':<4} | {'Strategy':<15} | {'Conviction':<10} | {'Norm P':<7} | {'Gate':<6} | {'Distance':<8} | {'HMM State':<10}")
    print("-" * 90)
    close_trades.sort(key=lambda x: x['dist'])
    for r in close_trades:
        print(f"{r['symbol']:<10} | {r['direction']:<4} | {r['strategy_type']:<15} | {r['conviction']:.4f}     | {r['norm_p']:.4f}  | {r['gate_threshold']:.2f} | {r['dist']:.4f}   | {r['hmm_state']:<10}")

    print("\n[3] TOP WATCHLIST ASSETS BY CONVICTION")
    print(f"{'Symbol':<10} | {'Dir':<4} | {'Strategy':<15} | {'Conviction':<10} | {'Norm P':<7} | {'Gate':<6} | {'Distance':<8} | {'HMM State':<10}")
    print("-" * 90)
    other_trades.sort(key=lambda x: x['norm_p'], reverse=True)
    for r in other_trades[:10]:
        print(f"{r['symbol']:<10} | {r['direction']:<4} | {r['strategy_type']:<15} | {r['conviction']:.4f}     | {r['norm_p']:.4f}  | {r['gate_threshold']:.2f} | {r['dist']:.4f}   | {r['hmm_state']:<10}")

if __name__ == "__main__":
    check_ready_trades()
