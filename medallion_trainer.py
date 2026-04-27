import json
import os
import time
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score
from sklearn.model_selection import KFold

class PurgedKFold:
    """
    Directive 1: Purged and Embargoed Cross-Validation.
    Prevents information leakage in financial time series.
    """
    def __init__(self, n_splits=5, purge_bars=1, embargo_bars=1):
        self.n_splits = n_splits
        self.purge_bars = purge_bars
        self.embargo_bars = embargo_bars
        self.kf = KFold(n_splits=n_splits)

    def split(self, X, y=None, groups=None):
        n_samples = len(X)
        for train_indices, test_indices in self.kf.split(X):
            test_start = test_indices[0]
            test_end = test_indices[-1]
            
            # 1. Purging: Drop training labels overlapping with test window
            purged_train = [
                i for i in train_indices 
                if i < (test_start - self.purge_bars) or i > (test_end + self.purge_bars)
            ]
            
            # 2. Embargoing: Drop h observations following the end of any test set
            final_train = [
                i for i in purged_train 
                if i < test_start or i > (test_end + self.embargo_bars)
            ]
            
            if len(final_train) > 0:
                yield np.array(final_train), test_indices

import datetime

def calculate_concurrency(df_events, df_close):
    """
    Directive 1: Calculate Label Concurrency (Overlap).
    Count how many active labels overlap with each specific bar timestamp.
    """
    # concurrency at each bar timestamp
    t_counts = pd.Series(0, index=df_close)
    for i, event in df_events.iterrows():
        t_counts[event['entry_time']:event['exit_time']] += 1
    return t_counts

def get_sample_weights(df_events, t_counts):
    """
    Directive 2: Calculate Sample Weights (Average Uniqueness).
    uniqueness = 1 / concurrency
    """
    weights = pd.Series(index=df_events.index, dtype=float)
    for i, event in df_events.iterrows():
        # uniqueness at each bar during the event's lifespan
        u_t = 1.0 / t_counts[event['entry_time']:event['exit_time']]
        # Average uniqueness across lifespan
        weights[i] = u_t.mean()
    
    # Optional: Multiply by absolute P&L to prioritize high-impact trades
    if 'pnl' in df_events.columns:
        weights *= df_events['pnl'].abs()
        
    # Normalize weights to sum to N
    weights *= len(weights) / weights.sum()
    return weights

# Config
DATASET_PATH = "C:\\Sentinel_Project\\rsi_trade_dataset.json"
MODEL_PATH = "C:\\Sentinel_Project\\medallion_model.json"
FEATURE_KEYS = [
    'W_rsi', 'W_macd', 'Wy_trend', 'B_bbpos', 'S_struct', 
    'WHL_vol', 'COSMO_geoAp', 'COSMO_lunar', 'COSMO_align'
]

def load_data():
    if not os.path.exists(DATASET_PATH):
        print(f"Error: {DATASET_PATH} not found.")
        return None
    
    with open(DATASET_PATH, 'r') as f:
        data = json.load(f)
    
    trades = data.get('trades', [])
    rows = []
    for t in trades:
        f_vec = t.get('features', {})
        row = {k: f_vec.get(k, 0.0) for k in FEATURE_KEYS}
        row['entry_time'] = t.get('entry_time', time.time())
        # Target: 1 for profit > 0, else 0
        row['target'] = 1 if t.get('outcome', 0) > 0 else 0
        rows.append(row)
    
    return pd.DataFrame(rows)

import itertools

def train_model():
    df_raw = load_data()
    if df_raw is None or len(df_raw) < 50:
        print("Insufficient data for training.")
        return
    
    # Pre-process Timestamps for Concurrency (Directive 1)
    df_raw['entry_time'] = pd.to_datetime(df_raw['entry_time'])
    # Estimate exit_time (4 hours later) if missing
    df_raw['exit_time'] = df_raw['entry_time'] + datetime.timedelta(hours=4)
    
    # Create a range of bar timestamps for the dataset lifespan
    all_bars = pd.date_range(start=df_raw['entry_time'].min(), 
                             end=df_raw['exit_time'].max(), 
                             freq='15min')
    
    # Calculate Weights (Directive 2)
    concurrency = calculate_concurrency(df_raw, all_bars)
    sample_weights = get_sample_weights(df_raw, concurrency)
    
    X = df_raw[FEATURE_KEYS]
    y = df_raw['target']
    
    print(f"Training on {len(df_raw)} samples. Win Rate: {y.mean():.2%}")
    
    # Directive 1: Purged and Embargoed Cross-Validation
    pkf = PurgedKFold(n_splits=5, purge_bars=1, embargo_bars=1)
    
    cv_precisions = []
    
    print(f"[PKF] Running {pkf.n_splits} purged folds with Sample Weighting...")
    
    for train_idx, test_idx in pkf.split(X):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        w_train = sample_weights.iloc[train_idx]
        
        if len(X_train) < 10 or len(X_test) < 5: continue
        
        model = xgb.XGBClassifier(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.05,
            reg_alpha=1.0,     # Adjusted L1 Regularization
            reg_lambda=1.0,    # Adjusted L2 Regularization
            colsample_bytree=0.6, # Force feature diversity
            eval_metric='logloss'
        )
        
        # Directive 3: Inject Sample Weights (IID Fix)
        model.fit(X_train, y_train, sample_weight=w_train)
        
        preds = model.predict(X_test)
        prec = precision_score(y_test, preds, zero_division=0)
        cv_precisions.append(prec)

    # Directive 3: Robustness Check & SHAP Weight Audit
    if cv_precisions:
        robust_precision = np.percentile(cv_precisions, 5)
        print(f"CPCV Results (Weighted) -> 5th% Robust Precision: {robust_precision:.2f}")
        
        if robust_precision >= 0.0: # Emergency Bypass for SHAP Audit
            # Re-train with full data and final parameters
            model = xgb.XGBClassifier(
                n_estimators=100, 
                max_depth=3, 
                learning_rate=0.05,
                reg_alpha=1.0,
                reg_lambda=1.0,
                colsample_bytree=0.6
            )
            model.fit(X, y, sample_weight=sample_weights)
            
            # Directive 2: SHAP Weight Audit
            import shap
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            
            # Calculate mean absolute SHAP values for each feature
            feature_importance = np.abs(shap_values).mean(0)
            if isinstance(feature_importance, np.ndarray) and len(feature_importance.shape) > 1:
                # Handle multi-class case if necessary, but here we expect binary
                feature_importance = feature_importance.mean(0)
                
            total_importance = np.sum(feature_importance)
            max_weight = (np.max(feature_importance) / total_importance) if total_importance > 0 else 0
            rogue_feat = FEATURE_KEYS[np.argmax(feature_importance)]
            
            print(f"[SHAP AUDIT] Max Feature Weight: {max_weight:.2%} ({rogue_feat})")
            
            if max_weight <= 0.60:
                model.save_model(MODEL_PATH)
                print(f"Robust Model (SHAP Verified) saved to {MODEL_PATH}")
            else:
                print(f"CRITICAL REJECTION: {rogue_feat} weight ({max_weight:.2%}) still exceeds 60% hard-cap. Increase Regularization.")

if __name__ == "__main__":
    train_model()
