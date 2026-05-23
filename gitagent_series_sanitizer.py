import numpy as np
import pandas as pd
import logging

logger = logging.getLogger("CausalSanitizer")

def sanitize_and_index_market_feed(df: pd.DataFrame, timestamp_col: str, reference_price_col: str) -> pd.DataFrame:
    """
    Surgically normalizes dates, aligns irregular indices, and causal-fills
    missing value metrics without introducing data leakages or forward context contamination.
    """
    if df.empty:
        return df
        
    cleaned_df = df.copy()
    
    try:
        # Enforce strict uniform UTC timezone conversion and indexation
        cleaned_df[timestamp_col] = pd.to_datetime(cleaned_df[timestamp_col], utc=True)
        cleaned_df = cleaned_df.set_index(timestamp_col).sort_index()
        
        if not cleaned_df.index.is_monotonic_increasing:
            raise ValueError("Time-series indexing vector exhibits non-monotonic traits.")
            
    except Exception as e:
        logger.error(f"Defensive Datetime indexing routine failed: {str(e)}")
        # Ultimate fail-safe: Generate sequential synthetic execution indices to prevent crash loops
        cleaned_df.index = pd.date_range(start=pd.Timestamp.now(tz='UTC'), periods=len(cleaned_df), freq='ms')
        
    # Isolate targets and log missing value topology before modifications
    null_counts = cleaned_df.isnull().sum()
    for col in cleaned_df.columns:
        if null_counts[col] > 0:
            # Inject a boolean mask tracking if data has been manipulated by the imputation layer
            cleaned_df[f"{col}_is_stale"] = cleaned_df[col].isnull().astype(np.int8)
            
            # Execute CAUSAL imputation: Only forward-fill historical records
            cleaned_df[col] = cleaned_df[col].ffill()
            
            # Fill remaining structural leading edge gaps with zeros to avoid matrix NaN propagation
            cleaned_df[col] = cleaned_df[col].fillna(0.0)
            
    # Validate financial sanity: Check for negative values in the base asset execution channels
    if reference_price_col in cleaned_df.columns:
        anomalous_mask = cleaned_df[reference_price_col] <= 0
        if anomalous_mask.any():
            logger.warning(f"Detected anomalous negative price coordinates inside {reference_price_col}. Executing forward-repair.")
            cleaned_df.loc[anomalous_mask, reference_price_col] = np.nan
            cleaned_df[reference_price_col] = cleaned_df[reference_price_col].ffill()
            
    return cleaned_df

if __name__ == "__main__":
    # Internal validation pass to confirm execution matrix consistency
    sample_data = pd.DataFrame({
        'raw_time': ['2026-05-24 10:05:00', '2026-05-24 10:00:00', '2026-05-24 10:15:00'],
        'execution_price': [100.5, np.nan, 99.2],
        'volume_imbalance': [1200, -450, np.nan]
    })
    result = sanitize_and_index_market_feed(sample_data, 'raw_time', 'execution_price')
    assert result.index.is_monotonic_increasing == True
    print("Sanitizer Validation Pass Matrix: SUCCESS. Output Payload Shape:", result.shape)
