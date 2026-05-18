import os
import sys
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import xgboost as xgb
from pathlib import Path

# Set path
sys.path.append(r"C:\Sentinel_Project")
import feature_engineering as feat_eng
import gitagent_sigproc as sigproc
from sentinel_slow_loop import optimize_fracdiff_d

PROJECT_ROOT = Path(r"C:\Sentinel_Project")
MODEL_PATH = PROJECT_ROOT / "data" / "sentinel_xgb_model.json"

def main():
    print("==================================================")
    print(" TRAINING ROBUST PRODUCTION XGBOOST META-MODEL")
    print("==================================================")
    
    if not mt5.initialize():
        print("[FAIL] MT5 Initialization failed.")
        return
        
    symbols = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY", "XAUUSD"]
    all_data = []
    
    for symbol in symbols:
        if not mt5.symbol_select(symbol, True):
            continue
            
        # Fetch larger history for robust training (1500 bars)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 1500)
        if rates is None or len(rates) < 1000:
            continue
            
        df_ta = pd.DataFrame(rates)
        df_ta['time'] = pd.to_datetime(df_ta['time'], unit='s')
        
        # Technical indicators
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
            
            # Label generation: next period return > 0
            df_ml['target'] = np.where(df_ml['close'].shift(-1) > df_ml['close'], 1, 0)
            
            # Drop the last row since its label is unknown
            all_data.append(df_ml.iloc[:-1])
            print(f"[OK] Preprocessed {symbol}: {len(df_ml) - 1} training samples.")
        except Exception as e:
            print(f"[FAIL] Prep failed for {symbol}: {e}")
            
    mt5.shutdown()
    
    if not all_data:
        print("[FAIL] No training data assembled.")
        return
        
    df_train_all = pd.concat(all_data, ignore_index=True)
    
    # Extract feature columns and targets
    X_raw = df_train_all.select_dtypes(include=[np.number])
    feature_cols = [c for c in X_raw.columns if c != 'target']
    
    X = X_raw[feature_cols]
    y = X_raw['target']
    
    print(f"\nFeature list: {feature_cols}")
    print(f"Total dataset shape: {X.shape} | Win Rate = {y.mean():.2%}")
    
    # Train Booster using native xgboost api
    dtrain = xgb.DMatrix(X, label=y)
    
    params = {
        'max_depth': 3,
        'eta': 0.05,
        'objective': 'binary:logistic',
        'eval_metric': 'logloss',
        'reg_alpha': 1.0,
        'reg_lambda': 1.0,
        'colsample_bytree': 0.7,
        'seed': 42
    }
    
    print("\nTraining XGBoost Booster model...")
    booster = xgb.train(params, dtrain, num_boost_round=60)
    
    # Verify save path directory exists
    os.makedirs(MODEL_PATH.parent, exist_ok=True)
    booster.save_model(str(MODEL_PATH))
    print(f"\n[SUCCESS] Robust booster model successfully saved to: {MODEL_PATH}")

if __name__ == "__main__":
    main()
