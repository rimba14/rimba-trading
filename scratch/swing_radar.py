import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys
import os

# Ensure project root is in path
sys.path.append(r'C:\Sentinel_Project')

from feature_engineering import ingest_mtf_ohlcv, compute_swing_alpha
from sentinel_config import WATCHLIST

def calculate_proximity():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    radar_data = []
    
    # Use a subset if watchlist is huge, but user said 44 assets
    for symbol in WATCHLIST[:44]:
        try:
            df_h1, df_h4 = ingest_mtf_ohlcv(symbol)
            if df_h1 is None or len(df_h1) < 50:
                continue
            
            alpha = compute_swing_alpha(df_h1, df_h4)
            latest = alpha.iloc[-1]
            latest_price = df_h1['close'].iloc[-1]
            
            # --- Proximity Metrics ---
            
            # 1. Mean Reversion Long (RSI distance to 35)
            rsi = latest['rsi']
            dist_rsi_long = max(0, rsi - 35)
            
            # 2. Mean Reversion Short (RSI distance to 65)
            dist_rsi_short = max(0, 65 - rsi)
            
            # 3. Trend Continuation (Price distance to 20 EMA)
            ema_20 = latest['ema_20']
            dist_ema_pct = (abs(latest_price - ema_20) / ema_20) * 100
            
            # Mock HMM Regime for now or fetch if possible (usually in arctic but let's stick to price for radar)
            # We'll just label based on EMA alignment
            regime = "BULL" if latest_price > latest['sma_50'] else "BEAR"
            
            # Best proximity (smallest relative distance)
            # We normalize or just pick the most interesting one
            
            radar_data.append({
                'symbol': symbol,
                'regime': regime,
                'rsi': rsi,
                'dist_rsi_long': dist_rsi_long,
                'dist_rsi_short': dist_rsi_short,
                'dist_ema_pct': dist_ema_pct,
                'ema_20': ema_20,
                'price': latest_price,
                'entropy': latest['entropy']
            })
            
        except Exception as e:
            continue

    # Sorting logic for Top 3 (excluding already triggered RSI overbought which is currently inactive)
    # We prioritize Trend Continuation (closest to EMA 20) and Mean Reversion Long (closest to 35)
    
    candidates = []
    for asset in radar_data:
        # Measure distance to closest valid setup
        # Setup 1: RSI < 35 (Long only)
        dist_rsi = max(0, asset['rsi'] - 35)
        
        # Setup 2: Price to 20 EMA
        dist_ema = asset['dist_ema_pct']
        
        # Setup 3: Catalyst (Hard to measure proximity simply, but let's stick to EMA/RSI)
        
        asset['proximity_score'] = min(dist_ema, dist_rsi / 5.0) # Weighted score
        candidates.append(asset)

    top_candidates = sorted(candidates, key=lambda x: x['proximity_score'])

    print("--- LIVE SWING RADAR (v26.0) ---")
    for asset in top_candidates[:3]:
        # Determine setup type
        dist_ema = asset['dist_ema_pct']
        dist_rsi = max(0, asset['rsi'] - 35)
        
        if dist_ema < dist_rsi / 5.0:
            setup = "Trend Continuation (Pullback to 20 EMA)"
            delta = f"Price is {dist_ema:.2f}% from 20 EMA ({asset['ema_20']:.5f}). Waiting for touch."
        else:
            setup = "Mean Reversion (Long Setup)"
            delta = f"RSI is {asset['rsi']:.2f}. Waiting for RSI < 35 (Delta: {dist_rsi:.2f})."
            
        print(f"SYMBOL: {asset['symbol']} | REGIME: {asset['regime']}")
        print(f"SETUP: {setup}")
        print(f"PROXIMITY: {delta}")
        print(f"ENTROPY: {asset['entropy']:.3f}")
        print("-" * 30)

    mt5.shutdown()

if __name__ == "__main__":
    calculate_proximity()
