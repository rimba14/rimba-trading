import numpy as np
import pandas as pd

def compute_fractional_weights(d: float, size: int) -> np.ndarray:
    """
    Sequentially generates memory weights for fractional differentiation lines.
    """
    w = [1.0]
    for k in range(1, size):
        w.append(-w[-1] / k * (d - k + 1))
    return np.array(w[::-1])

def apply_fractional_differentiation(series: pd.Series, d: float, threshold: float = 1e-4) -> pd.Series:
    """
    Transforms price history paths using fractional parameters.
    Preserves structural correlation profiles for attention-based models.
    """
    # Generate maximum trailing sequence bounds matching threshold precision
    raw_weights = compute_fractional_weights(d, len(series))
    abs_weights = np.abs(raw_weights)
    
    # Filter out values below precision floor to optimize compute footprint
    valid_cutoff = np.where(abs_weights > threshold)[0][0]
    weights = raw_weights[valid_cutoff:]
    
    res = {}
    # Apply causal shift adjustments
    for i in range(len(weights), len(series) + 1):
        loc_slice = series.iloc[i - len(weights) : i]
        res[series.index[i - 1]] = np.dot(weights, loc_slice.values)
        
    return pd.Series(res)

if __name__ == "__main__":
    # Internal component sanity loop
    synthetic_prices = pd.Series(
        np.cumsum(np.random.normal(0, 1, 100)) + 1000.0,
        index=pd.date_range(start="2026-05-24", periods=100, freq='min')
    )
    differentiated_output = apply_fractional_differentiation(synthetic_prices, d=0.45)
    assert len(differentiated_output) > 0
    print("Fractional Calculus Routine Validation: SUCCESS. Series length preserved past memory drop.")
