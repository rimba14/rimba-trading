import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from dataclasses import dataclass
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import RandomForestClassifier

PROJECT_ROOT = Path(r"C:\Sentinel_Project")
sys.path.append(str(PROJECT_ROOT))

import MetaTrader5 as mt5
import feature_engineering as feat_eng

@dataclass
class BacktestConfig:
    """
    Encapsulates Reality Tax parameters for backtesting.
    """
    flat_commission: float = 3.00
    swap_charge: float = 5.00
    pip_multiplier: int = 100000
    default_spread: float = 1.2

class StrategyFailed(Warning):
    """Custom warning thrown when the backtest Sharpe ratio fails to clear the Reality Tax threshold."""
    pass

def compute_strategy_metrics(trades_df, initial_capital=10000):
    """
    SRE Patched: trades_df must have ['close_time', 'pnl_net']
    """
    if trades_df.empty:
        return {}

    pnl = trades_df['pnl_net'].values
    
    # 1. Base Metrics
    win_rate = (pnl > 0).mean()
    avg_win = pnl[pnl > 0].mean() if (pnl > 0).any() else 0.0
    avg_loss = abs(pnl[pnl < 0].mean()) if (pnl < 0).any() else 0.0
    profit_factor = (pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else np.inf
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # 2. Equity Curve & Drawdown (Capital Adjusted)
    cumulative_equity = initial_capital + np.cumsum(pnl)
    rolling_max = np.maximum.accumulate(cumulative_equity)
    drawdown_pct = (cumulative_equity - rolling_max) / rolling_max
    max_dd = abs(drawdown_pct.min())

    # 3. Resample to Daily for Accurate Sharpe/Sortino
    # Requires 'close_time' as a datetime column in trades_df
    trades_df['close_time'] = pd.to_datetime(trades_df['close_time'])
    daily_pnl = trades_df.set_index('close_time')['pnl_net'].resample('D').sum().fillna(0)
    daily_returns = daily_pnl / initial_capital  # Simplified daily return
    
    mean_daily_ret = np.mean(daily_returns)
    std_daily_ret = np.std(daily_returns) + 1e-9
    
    sharpe = (mean_daily_ret / std_daily_ret) * np.sqrt(252)
    
    downside_returns = daily_returns[daily_returns < 0]
    sortino_neg = np.std(downside_returns) if len(downside_returns) > 0 else 1e-9
    sortino = (mean_daily_ret / sortino_neg) * np.sqrt(252)
    
    annual_return = (cumulative_equity[-1] - initial_capital) / initial_capital * (252 / len(daily_returns))
    calmar = annual_return / (max_dd + 1e-9)

    # Return RAW FLOATS for the optimizer. Format only on print.
    metrics = {
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_dd_pct": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "total_trades": len(trades_df)
    }
    return metrics

def monte_carlo_path_stress(pnl_array, initial_capital=10000, n_simulations=1000):
    """
    SRE Patched: Shuffles trade order to stress-test Maximum Drawdown and Calmar Ratio.
    Proves if the strategy survives 'bad luck' sequencing.
    """
    if len(pnl_array) < 10:
        return {"pass": False, "reason": "Not enough trades"}

    def calc_max_dd(pnl_seq):
        equity = initial_capital + np.cumsum(pnl_seq)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        return abs(drawdown.min())

    # Calculate baseline drawdown
    original_mdd = calc_max_dd(pnl_array)
    
    # Run Monte Carlo permutations
    shuffled_mdds = []
    for _ in range(n_simulations):
        shuffled = np.random.permutation(pnl_array)
        shuffled_mdds.append(calc_max_dd(shuffled))
        
    shuffled_mdds = np.array(shuffled_mdds)
    
    # If the original DD is worse than the 95th percentile of random shuffles,
    # the original backtest sequence was actually UNUSUALLY unlucky (Robust).
    # If the original DD is better than the 5th percentile, the backtest was UNUSUALLY lucky (Fragile).
    
    median_shuffled_dd = np.median(shuffled_mdds)
    worst_shuffled_dd = np.max(shuffled_mdds)
    percentile = (shuffled_mdds < original_mdd).mean() 
    
    print(f"Original Max DD:      {original_mdd:.2%}")
    print(f"Median Shuffled DD:   {median_shuffled_dd:.2%}")
    print(f"Worst Case Sim DD:    {worst_shuffled_dd:.2%}")
    print(f"Luck Percentile:      {percentile:.1%} (Lower = Luckier backtest sequence)")
    
    # Veto if the backtest DD was artificially lucky (bottom 10% of possible outcomes)
    # OR if the median shuffled DD blows past our 15% hard limit.
    passed = percentile > 0.10 and median_shuffled_dd < 0.15
    
    return {
        "pass": passed,
        "original_mdd": original_mdd,
        "median_sim_mdd": median_shuffled_dd,
        "worst_sim_mdd": worst_shuffled_dd
    }

def simulate_oos_trading(test_df, probs, config: BacktestConfig = None):
    """
    Simulates Out-Of-Sample (OOS) trading on a given fold's test data.
    Applies Reality Tax: commissions, slippage, and overnight swaps.
    """
    if config is None:
        config = BacktestConfig()

    fold_trades_pnl = []
    oos_trades_log = []
    
    close_prices = test_df['close'].values
    times = test_df.index

    for idx in range(len(test_df) - 1):
        prob = probs[idx]
        
        # Simple threshold trade entries
        if prob > 0.55 or prob < 0.45:
            direction = 1 if prob > 0.55 else -1
            entry_price = close_prices[idx]

            # Hold for 4 bars or until exit
            exit_idx = min(idx + 4, len(test_df) - 1)
            exit_price = close_prices[exit_idx]

            # Gross P&L
            gross_pnl = direction * (exit_price - entry_price) * config.pip_multiplier

            # Retrieve spread in pips (points / 10 if standard MT5 broker)
            spread_val = test_df['spread'].iloc[idx] / 10.0 if 'spread' in test_df.columns else config.default_spread

            # ── Apply the Reality Tax ──
            # 1. Slippage penalty: 1.0x spread
            slippage_penalty = spread_val * 10.0 # Standard lot pip value

            # 2. Swap penalty: check if held overnight past 23:55
            held_overnight = False
            for t_offset in range(idx, exit_idx):
                if times[t_offset].hour == 23 and times[t_offset].minute >= 50:
                    held_overnight = True
                    break

            swap_penalty = config.swap_charge if held_overnight else 0.0

            net_pnl = gross_pnl - slippage_penalty - config.flat_commission - swap_penalty
            fold_trades_pnl.append(net_pnl)

            oos_trades_log.append({
                "close_time": times[exit_idx],
                "pnl_net": net_pnl
            })

    return fold_trades_pnl, oos_trades_log

def run_walk_forward_audit(df, feature_cols, n_folds=5):
    """
    Executes the walk-forward backtest by iterating through chronological folds.
    Returns aggregated OOS predictions, targets, and trade logs.
    """
    n_samples = len(df)
    fold_size = n_samples // (n_folds + 1)
    
    print(f" Dataset size: {n_samples} bars | Fold size: {fold_size} bars")
    
    oos_preds = []
    oos_targets = []
    oos_trades_log = []
    
    # Parameters for Reality Tax
    bt_config = BacktestConfig(
        flat_commission=3.00,
        swap_charge=5.00,
        pip_multiplier=100000,
        default_spread=1.2
    )
    
    print("\n--- FOLD-BY-FOLD WALK-FORWARD AUDIT ---")
    
    for fold in range(n_folds):
        train_end = (fold + 1) * fold_size
        test_end = train_end + fold_size
        
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end:test_end]
        
        X_train, y_train = train_df[feature_cols], train_df['target']
        X_test, y_test = test_df[feature_cols], test_df['target']
        
        model = RandomForestClassifier(n_estimators=50, random_state=42 + fold)
        model.fit(X_train, y_train)
        
        probs = model.predict_proba(X_test)[:, 1]
        fold_auc = roc_auc_score(y_test, probs)
        
        fold_trades_pnl, fold_oos_log = simulate_oos_trading(test_df, probs, config=bt_config)
        
        fold_net_profit = np.sum(fold_trades_pnl) if len(fold_trades_pnl) > 0 else 0.0
        print(f" Fold {fold+1} | Train: 0-{train_end} | Test: {train_end}-{test_end} | OOS AUC: {fold_auc:.4f} | Net Trades profit: ${fold_net_profit:.2f}")
        
        oos_preds.extend(probs)
        oos_targets.extend(y_test)
        oos_trades_log.extend(fold_oos_log)
        
    return oos_preds, oos_targets, oos_trades_log

def validate_strategy_performance(oos_preds, oos_targets, oos_trades_log, initial_capital=10000):
    """
    Aggregates OOS metrics, runs Monte Carlo stress tests, and enforces validation gates.
    """
    stitched_auc = roc_auc_score(oos_targets, oos_preds)
    trades_df = pd.DataFrame(oos_trades_log)
    
    metrics = compute_strategy_metrics(trades_df, initial_capital=initial_capital)
    sharpe_ratio = metrics.get("sharpe", 0.0)
    sortino_ratio = metrics.get("sortino", 0.0)
    calmar_ratio = metrics.get("calmar", 0.0)
    max_drawdown = metrics.get("max_dd_pct", 0.0)
    win_rate = metrics.get("win_rate", 0.0)
    profit_factor = metrics.get("profit_factor", 0.0)
    
    print("\n==================================================")
    print("--- FINAL AGGREGATED OOS METRICS (SRE AUDIT) ---")
    print(f" Stitched OOS AUC-ROC    : {stitched_auc:.4f}")
    print(f" Total Closed Trades     : {metrics.get('total_trades', 0)}")
    print(f" Win Rate                : {win_rate:.2%}")
    print(f" Profit Factor           : {profit_factor:.4f}")
    print(f" Max Drawdown %          : {max_drawdown:.2%}")
    print(f" Reality-Tax Sharpe Ratio : {sharpe_ratio:.4f}")
    print(f" Reality-Tax Sortino     : {sortino_ratio:.4f}")
    print(f" Reality-Tax Calmar      : {calmar_ratio:.4f}")
    
    print("\n Running Monte Carlo path dependency stress test...")
    mc_results = monte_carlo_path_stress(trades_df['pnl_net'].values, initial_capital=initial_capital)
    
    # Sharpe Ratio and Monte Carlo threshold gate
    if sharpe_ratio < 1.0 or not mc_results.get("pass", True):
        print("\n [CRITICAL WARNING] [StrategyFailed] Strategy failed backtest validation gates!")
        if sharpe_ratio < 1.0:
            print("  Sharpe Ratio is below the institutional requirement of 1.0.")
        if not mc_results.get("pass", True):
            print("  Monte Carlo Path Stress Veto: Strategy is fragile or path-dependent (median MDD >= 15% or sequence was unusually lucky).")
        print("  Wall 0 Veto active. Backtest rejected.")
        # Raise standard warning format
        import warnings
        warnings.warn("Strategy failed backtest validation gates!", StrategyFailed)
    else:
        print("\n [PASS] Strategy survives the Reality Tax & Monte Carlo Path Stress gates!")

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

    # 2. Walk-Forward Audit
    oos_preds, oos_targets, oos_trades_log = run_walk_forward_audit(df, feature_cols)

    # 3. Final Validation
    validate_strategy_performance(oos_preds, oos_targets, oos_trades_log)
        
    print("==================================================")
    print(" [OK] INSTITUTIONAL BACKTEST SIMULATION COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    main()
