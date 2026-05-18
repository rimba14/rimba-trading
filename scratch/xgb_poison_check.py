import os
import sys
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

# Set path
sys.path.append(r"C:\Sentinel_Project")
import feature_engineering as feat_eng
import gitagent_sigproc as sigproc
from sentinel_slow_loop import optimize_fracdiff_d

def main():
    print("==================================================")
    print(" XGBOOST FEATURE POISONING DIAGNOSTIC SCRIPT")
    print("==================================================")
    
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization failed.")
        return
        
    symbols = ["EURUSD", "GBPUSD"]
    feature_dfs = {}
    
    for symbol in symbols:
        if not mt5.symbol_select(symbol, True):
            print(f"[FAIL] Could not select {symbol}")
            continue
            
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 750)
        if rates is None or len(rates) < 512:
            print(f"[FAIL] Insufficient data for {symbol}")
            continue
            
        df_ta = pd.DataFrame(rates)
        df_ta['time'] = pd.to_datetime(df_ta['time'], unit='s')
        
        # Feature Calculations (standard tech indicators)
        c = df_ta["close"]
        delta = c.diff()
        gain  = delta.where(delta > 0, 0).rolling(14).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df_ta["W_rsi"]    = 100 - (100 / (1 + gain / (loss + 1e-9)))
        
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd  = ema12 - ema26
        df_ta["W_macd"]   = macd - macd.ewm(span=9, adjust=False).mean()
        
        ema20 = c.ewm(span=20, adjust=False).mean()
        ema50 = c.ewm(span=50, adjust=False).mean()
        df_ta["Wy_trend"] = (ema20 - ema50) / (c * 0.01 + 1e-9)
        
        ma20  = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        df_ta["B_bbpos"]  = (c - (ma20 - 2*std20)) / (4*std20 + 1e-9)
        df_ta["WHL_vol"]  = c.pct_change().rolling(20).std()
        df_ta["S_struct"]  = 0.5
        
        # Fractionally Differentiated Features
        df_ml = df_ta.copy()
        for col in ["open", "high", "low", "close"]:
            opt_d, fd = optimize_fracdiff_d(df_ta[col].values)
            pad = len(df_ta) - len(fd)
            norm_fd = sigproc.strict_normalize(fd)
            df_ml[col] = np.pad(norm_fd, (pad, 0), mode="edge")
            
        try:
            df_ml = feat_eng.engineer_features(
                df_ml,
                price_col="close",
                volume_col="tick_volume" if "tick_volume" in df_ml.columns else "volume",
                frac_d=0.45,
                fft_top_k=3,
                cs_rank=0.5,
            )
            df_ml = df_ml.dropna()
            feature_dfs[symbol] = df_ml
            print(f"[OK] Extracted features for {symbol}: shape={df_ml.shape}")
        except Exception as e:
            print(f"[FAIL] Feature engineering failed for {symbol}: {e}")
            
    mt5.shutdown()
    
    if len(feature_dfs) < 2:
        print("[FAIL] Missing feature dataframes for comparison.")
        return
        
    eur_df = feature_dfs["EURUSD"]
    gbp_df = feature_dfs["GBPUSD"]
    
    # Select numeric columns exactly as passed to model.predict
    eur_numeric = eur_df.select_dtypes(include=[np.number])
    gbp_numeric = gbp_df.select_dtypes(include=[np.number])
    
    print("\n--- NaN AND VARIANCE AUDIT ---")
    
    # 1. NaN and Inf Check
    for symbol, df in [("EURUSD", eur_numeric), ("GBPUSD", gbp_numeric)]:
        nans = df.isna().sum().sum()
        infs = np.isinf(df).sum().sum()
        nulls = df.isnull().sum().sum()
        print(f"{symbol}: NaNs={nans}, Infs={infs}, Nulls={nulls}")
        if nans + infs + nulls > 0:
            print(f"  [WARN] Corrupted columns in {symbol}:")
            print(df.isna().sum()[df.isna().sum() > 0])
            print(np.isinf(df).sum()[np.isinf(df).sum() > 0])
            
    # 2. Compare Vectors (EURUSD vs GBPUSD)
    print("\n--- COLUMN DIVERGENCENCE & STRUCTURAL AUDIT ---")
    common_cols = eur_numeric.columns.intersection(gbp_numeric.columns)
    
    eur_final = eur_numeric.iloc[-1]
    gbp_final = gbp_numeric.iloc[-1]
    
    for col in common_cols:
        val_eur = eur_final[col]
        val_gbp = gbp_final[col]
        var_eur = eur_numeric[col].var()
        var_gbp = gbp_numeric[col].var()
        
        is_identical = np.allclose(val_eur, val_gbp, atol=1e-7) if not (pd.isna(val_eur) or pd.isna(val_gbp)) else False
        is_zero_variance = (var_eur < 1e-9) or (var_gbp < 1e-9)
        
        status = "OK"
        if is_identical:
            status = "⚠️ IDENTICAL VALUE"
        if is_zero_variance:
            status = "🚨 ZERO VARIANCE"
            
        print(f"Feature: {col:<20} | EUR={val_eur:12.6f} (var={var_eur:12.6e}) | GBP={val_gbp:12.6f} (var={var_gbp:12.6e}) | {status}")

if __name__ == "__main__":
    main()
