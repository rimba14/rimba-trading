import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import RandomForestClassifier

PROJECT_ROOT = Path(r"C:\Sentinel_Project")
sys.path.append(str(PROJECT_ROOT))

import MetaTrader5 as mt5
import feature_engineering as feat_eng

class StrategyFailed(Warning):
    """Custom warning thrown when the backtest Sharpe ratio fails to clear the Reality Tax threshold."""
    pass

def fetch_data():
    """Fetches H1 historical candles for EURUSD or falls back to high-fidelity synthetic candles if offline."""
    df = None
    use_synthetic = False
    
    if mt5.initialize():
        # Fetch 2000 H1 candles to have enough data for 5 robust walk-forward folds
        rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 2000)
        if rates is not None and len(rates) >= 1000:
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            print(f" Loaded {len(df)} real EURUSD H1 candles from MT5.")
        else:
            use_synthetic = True
        mt5.shutdown()
    else:
        use_synthetic = True
        
    if use_synthetic or df is None:
        print(" [WARN] MT5 offline. Generating 2,000 synthetic high-fidelity bars.")
        np.random.seed(42)
        idx = pd.date_range(start="2026-01-01", periods=2000, freq="1h")
        close = 1.1500 + np.cumsum(np.random.normal(0, 0.0005, 2000))
        high = close + abs(np.random.normal(0.0002, 0.0001, 2000))
        low = close - abs(np.random.normal(0.0002, 0.0001, 2000))
        open_val = close + np.random.normal(0, 0.0001, 2000)
        
        df = pd.DataFrame({
            "open": open_val,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": np.random.randint(100, 1000, 2000),
            "spread": np.random.randint(10, 15, 2000) # points
        }, index=idx)
        
    return df

def main():
    print("==================================================")
    print(" [SRE WALK-FORWARD] INSTITUTIONAL BACKTEST ENGINE")
    print("==================================================")
    
    df = fetch_data()
    
    # 1. Feature Engineering (pure forward-only, lookahead-free!)
    print(" Running lookahead-free feature engineering...")
    df = feat_eng.engineer_features(df)
    
    # Generate predictive target: next H1 return direction (lookahead strictly inside target labels only!)
    df['future_return'] = df['close'].shift(-1) - df['close']
    df['target'] = np.where(df['future_return'] > 0, 1, 0)
    
    # Features list matching feature_engineering output
    feature_cols = ['frac_diff_price', 'fft_amp_1', 'fft_amp_2', 'fft_amp_3', 'order_flow_entropy']
    df.dropna(subset=feature_cols + ['target'], inplace=True)
    
    # 2. Expanding Window Split
    n_samples = len(df)
    n_folds = 5
    fold_size = n_samples // (n_folds + 1)
    
    print(f" Dataset size: {n_samples} bars | Fold size: {fold_size} bars")
    
    oos_preds = []
    oos_targets = []
    oos_trades_returns = []
    
    # Parameters for Reality Tax
    flat_commission = 3.00   # USD per trade
    swap_charge = 5.00       # USD per overnight carry
    pip_multiplier = 100000  # Standard EURUSD lot pip multiplier
    default_spread = 1.2     # pips (if spread not in points)
    
    print("\n--- FOLD-BY-FOLD WALK-FORWARD AUDIT ---")
    
    for fold in range(n_folds):
        # Chronological expanding training index: from beginning up to fold * fold_size
        train_end = (fold + 1) * fold_size
        test_end = train_end + fold_size
        
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        
        X_train, y_train = train_df[feature_cols], train_df['target']
        X_test, y_test = test_df[feature_cols], test_df['target']
        
        # Chronological train -> test validation
        model = RandomForestClassifier(n_estimators=50, random_state=42 + fold)
        model.fit(X_train, y_train)
        
        probs = model.predict_proba(X_test)[:, 1]
        fold_auc = roc_auc_score(y_test, probs)
        
        # Simulate OOS Trading on this fold
        fold_trades_pnl = []
        for idx in range(len(test_df) - 1):
            prob = probs[idx]
            close_prices = test_df['close'].values
            times = test_df.index
            
            # Simple threshold trade entries
            if prob > 0.55 or prob < 0.45:
                direction = 1 if prob > 0.55 else -1
                entry_price = close_prices[idx]
                
                # Hold for 4 bars or until exit
                exit_idx = min(idx + 4, len(test_df) - 1)
                exit_price = close_prices[exit_idx]
                
                # Gross P&L
                gross_pnl = direction * (exit_price - entry_price) * pip_multiplier
                
                # Retrieve spread in pips (points / 10 if standard MT5 broker)
                spread_val = test_df['spread'].iloc[idx] / 10.0 if 'spread' in test_df.columns else default_spread
                
                # ── Apply the Reality Tax ──
                # 1. Slippage penalty: 1.0x spread
                slippage_penalty = spread_val * 10.0 # Standard lot pip value
                
                # 2. Swap penalty: check if held overnight past 23:55
                held_overnight = False
                for t_offset in range(idx, exit_idx):
                    if times[t_offset].hour == 23 and times[t_offset].minute >= 50:
                        held_overnight = True
                        break
                        
                swap_penalty = swap_charge if held_overnight else 0.0
                
                net_pnl = gross_pnl - slippage_penalty - flat_commission - swap_penalty
                fold_trades_pnl.append(net_pnl)
                oos_trades_returns.append(net_pnl)
                
        fold_trades_pnl = np.array(fold_trades_pnl)
        fold_net_profit = np.sum(fold_trades_pnl) if len(fold_trades_pnl) > 0 else 0.0
        
        print(f" Fold {fold+1} | Train: 0-{train_end} | Test: {train_end}-{test_end} | OOS AUC: {fold_auc:.4f} | Net Trades profit: ${fold_net_profit:.2f}")
        
        oos_preds.extend(probs)
        oos_targets.extend(y_test)
        
    # 3. Stitch OOS metrics together
    stitched_auc = roc_auc_score(oos_targets, oos_preds)
    oos_trades_returns = np.array(oos_trades_returns)
    
    # Calculate Sharpe Ratio after the Reality Tax
    if len(oos_trades_returns) > 1:
        mean_ret = np.mean(oos_trades_returns)
        std_ret = np.std(oos_trades_returns) + 1e-9
        # Annualized Sharpe (assuming standard daily-frequency equivalent trade distributions)
        sharpe_ratio = (mean_ret / std_ret) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0
        
    print("\n==================================================")
    print("--- FINAL AGGREGATED OOS METRICS ---")
    print(f" Stitched OOS AUC-ROC    : {stitched_auc:.4f}")
    print(f" Total Closed Trades     : {len(oos_trades_returns)}")
    print(f" Aggregated Net OOS P&L  : ${np.sum(oos_trades_returns):.2f}")
    print(f" Reality-Tax Sharpe Ratio : {sharpe_ratio:.4f}")
    
    # Sharpe Ratio threshold gate
    if sharpe_ratio < 1.0:
        print("\n [CRITICAL WARNING] [StrategyFailed] Strategy failed the Reality Tax!")
        print("  Sharpe Ratio is below the institutional requirement of 1.0.")
        print("  Wall 0 Veto active. Backtest rejected due to high friction sensitivity.")
        # Raise standard warning format
        import warnings
        warnings.warn("Strategy failed the Reality Tax Sharpe ratio threshold (< 1.0)!", StrategyFailed)
    else:
        print("\n [PASS] Strategy survives the Reality Tax with institutional Sharpe >= 1.0!")
        
    print("==================================================")
    print(" [OK] INSTITUTIONAL BACKTEST SIMULATION COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    main()
