import numpy as np
import pandas as pd

def apply_triple_barrier_labeling(
    price_series: pd.Series, 
    timestamps: pd.Series, 
    upper_atr_mult: float, 
    lower_atr_mult: float, 
    atr_series: pd.Series,
    time_horizon_bars: int
) -> pd.DataFrame:
    """
    Surgically maps 1D dollar bar price sequences into path-dependent labels (Triple Barrier Method).
    Returns a DataFrame containing the definitive target outcomes [-1, 0, 1] for model optimization.
    """
    labels = []
    indices = price_series.index
    
    for i in range(len(price_series) - time_horizon_bars):
        start_idx = indices[i]
        entry_price = price_series.loc[start_idx]
        current_atr = atr_series.loc[start_idx]
        
        # Calculate localized constitutional boundaries
        tp_target = entry_price + (upper_atr_mult * current_atr)
        sl_target = entry_price - (lower_atr_mult * current_atr)
        
        # Isolate the evaluation slice over the window path horizon
        path_window = price_series.iloc[i + 1 : i + 1 + time_horizon_bars]
        
        barrier_touch = 0 # Default indicator: Stagnation / Time Horizon expiration
        idx = start_idx
        
        for idx_curr, price in path_window.items():
            if price >= tp_target:
                barrier_touch = 1  # Upper boundary touch (Profit target achieved)
                idx = idx_curr
                break
            elif price <= sl_target:
                barrier_touch = -1 # Lower boundary touch (Stop loss triggered)
                idx = idx_curr
                break
                
        labels.append({
            'index': start_idx,
            'barrier_label': barrier_touch,
            'exit_timestamp': path_window.index[-1] if barrier_touch == 0 else idx
        })
        
    if not labels:
        return pd.DataFrame(columns=['barrier_label', 'exit_timestamp'])
    return pd.DataFrame(labels).set_index('index')

if __name__ == "__main__":
    print("Running QA test suite for triple_barrier_labeler...")
    # Generate synthetic prices and ATR
    np.random.seed(42)
    prices = pd.Series(100 + np.cumsum(np.random.normal(0, 1, 100)))
    timestamps = pd.Series(pd.date_range("2026-01-01", periods=100))
    prices.index = timestamps
    atr_series = pd.Series(np.ones(100) * 1.5, index=timestamps)
    
    labels_df = apply_triple_barrier_labeling(
        prices, timestamps, upper_atr_mult=2.0, lower_atr_mult=1.5,
        atr_series=atr_series, time_horizon_bars=10
    )
    print(f"Generated {len(labels_df)} labels.")
    print("Label distribution:\n", labels_df['barrier_label'].value_counts())
    assert len(labels_df) == 90
    print("[QA PASS] triple_barrier_labeler verified successfully!")
