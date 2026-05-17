import sys
import os
import time
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

PROJECT_ROOT = r"C:\Sentinel_Project"
sys.path.append(PROJECT_ROOT)

# Active Universe
SYMBOLS = ["EURUSD", "EURPLN", "ETHUSD", "ADAUSD", "SOLUSD"]

def get_30d_avg_spread(symbol):
    """Retrieves the 30-day average spread, ignoring the 23:55-00:15 rollover window."""
    # Fetch 30 days of H1 bars (30 * 24 = 720 bars)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 720)
    if rates is None or len(rates) == 0:
        return 0.0
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    # Filter out hour 23 and hour 0 to ignore the 23:55-00:15 daily rollover window
    clean_df = df[~df['datetime'].dt.hour.isin([23, 0])]
    if clean_df.empty:
        return float(df['spread'].mean())
    return float(clean_df['spread'].mean())

def audit_bars(symbol, timeframe, count, name):
    tf_seconds = 3600 if timeframe == mt5.TIMEFRAME_H1 else 14400
    
    # 1. & 2. Exactly 100 bars retrieved
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) != count:
        return {
            "status": "FAIL",
            "issues": [f"Retrieved {len(rates) if rates is not None else 0} bars (Expected exactly {count})"]
        }
        
    df = pd.DataFrame(rates)
    issues = []
    
    # 3. No NaN in OHLCV columns (not just filled - actually present)
    ohlcv_cols = ['open', 'high', 'low', 'close', 'tick_volume']
    for col in ohlcv_cols:
        if col not in df.columns:
            issues.append(f"Column '{col}' is missing")
        elif df[col].isnull().any():
            issues.append(f"NaN present in '{col}' column")
            
    # 4. Timestamps monotonic, no duplicates, no gaps > 2x timeframe (allowing for weekend gap exception)
    if 'time' not in df.columns:
        issues.append("Column 'time' is missing")
    else:
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        
        # Check monotonicity
        if not df['time'].is_monotonic_increasing:
            issues.append("Timestamps are not monotonically increasing")
            
        # Check duplicates & gaps
        gaps = df['time'].diff().dropna()
        if (gaps == 0).any():
            issues.append("Duplicate timestamps detected")
            
        # Check for gaps > 2x timeframe
        large_gaps = []
        for i, gap in enumerate(gaps):
            if gap > 2 * tf_seconds:
                prev_time = df['datetime'].iloc[i]
                next_time = df['datetime'].iloc[i+1]
                # Check if gap is over weekend (Friday evening to Sunday night)
                is_weekend = (prev_time.weekday() == 4 and next_time.weekday() == 0) or \
                             (prev_time.weekday() == 4 and next_time.weekday() == 6) or \
                             (prev_time.weekday() == 5 or prev_time.weekday() == 6)
                if not is_weekend:
                    large_gaps.append(f"{prev_time} -> {next_time} ({gap/tf_seconds:.1f}x tf)")
                    
        if large_gaps:
            issues.append(f"Gaps > 2x timeframe: {', '.join(large_gaps[:3])}")

    # 5. Spread at each bar within 3x the 30-day average spread
    avg_spread = get_30d_avg_spread(symbol)
    if 'spread' in df.columns and avg_spread > 0:
        abnormal_spreads = df[(df['spread'] > 3 * avg_spread) & (df['spread'] > 0)]
        if not abnormal_spreads.empty:
            issues.append(f"Spread exceeds 3x 30d avg ({avg_spread:.1f} points) in {len(abnormal_spreads)} bars")
            
    # Check for price outliers (H > 5*L ratio)
    if 'high' in df.columns and 'low' in df.columns:
        outliers = df[df['low'] > 0]
        if ((outliers['high'] / outliers['low']) > 5.0).any():
            issues.append("Corrupt tick: H/L ratio > 5")

    # 6. Volume is non-zero for at least 95% of bars
    if 'tick_volume' in df.columns:
        zero_vol_pct = (df['tick_volume'] == 0).mean()
        if zero_vol_pct > 0.05:
            issues.append(f"Zero-volume bars exceed 5% limit ({zero_vol_pct * 100:.1f}%)")
            
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "bars": len(df)
    }

def main():
    print("==================================================")
    print(" [AUDIT] STARTING HISTORICAL DATA QUALITY AUDIT (MT5)")
    print("==================================================")
    
    if not mt5.initialize():
        print("CRITICAL: Failed to initialize MT5!")
        sys.exit(1)
        
    for sym in SYMBOLS:
        print(f"\nEvaluating Symbol: {sym}")
        sym_info = mt5.symbol_info(sym)
        if sym_info is None:
            print(f"  [ERROR] Symbol {sym} not found in terminal!")
            continue
            
        for tf, name in [(mt5.TIMEFRAME_H1, "H1"), (mt5.TIMEFRAME_H4, "H4")]:
            res = audit_bars(sym, tf, 100, name)
            status_str = "PASS" if res['status'] == "PASS" else "FAIL"
            print(f"  [{name}] Status: {status_str}")
            if res['issues']:
                for issue in res['issues']:
                    print(f"    [WARN] {issue}")
            else:
                print("    [OK] All checks passed (100% clean data).")
                
    mt5.shutdown()
    print("\n==================================================")
    print(" [OK] AUDIT COMPLETED SUCCESSFULLY")
    print("==================================================")

if __name__ == "__main__":
    main()
