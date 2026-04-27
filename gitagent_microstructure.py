import numpy as np
import pandas as pd

def calculate_roll_spread(close_prices):
    """
    Roll (1984) Bid-Ask Spread Estimate.
    Spread = 2 * sqrt(-cov(delta_p_t, delta_p_{t-1}))
    """
    if len(close_prices) < 3:
        return 0.0
    
    diffs = np.diff(close_prices)
    cov = np.cov(diffs[:-1], diffs[1:])
    
    if cov.size == 1:
        val = cov.item() # Single value
    else:
        val = cov[0, 1]
        
    if val < 0:
        return 2 * np.sqrt(-val)
    else:
        return 0.0 # Covariance is positive, Roll spread is zero/invalid

def calculate_corwin_schultz(high, low):
    """
    Corwin-Schultz (2012) Spread Estimate.
    Uses high-low ratios over two consecutive bars.
    """
    if len(high) < 2:
        return 0.0
        
    # 1. Calculate Gamma: [log(H_t / L_t)]^2
    gamma = (np.log(high / low)**2)
    
    # 2. Calculate Beta: sum of gamma over two bars
    beta = gamma[:-1] + gamma[1:]
    
    # 3. Calculate Sigma: log(max(H_t, H_{t-1}) / min(L_t, L_{t-1}))^2
    h2 = np.maximum(high[:-1], high[1:])
    l2 = np.minimum(low[:-1], low[1:])
    sigma = (np.log(h2 / l2)**2)
    
    # 4. Spread Formula
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / (3 - 2 * np.sqrt(2)) - np.sqrt(sigma / (3 - 2 * np.sqrt(2)))
    # S = 2 * (exp(alpha) - 1) / (1 + exp(alpha))
    spread = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    
    # Clean up negative values (which happen in noisy markets)
    spread = np.maximum(0, spread)
    return np.mean(spread)

def get_microstructure_score(df):
    """
    Returns a score from 0 (Toxic/Poor Liquidity) to 100 (Clean/High Liquidity)
    """
    try:
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # 1. Roll Spread (Internal Noise)
        roll = calculate_roll_spread(close[-50:])
        # Normalize: Roll spread relative to price. 0.001 (10 pips) is "High"
        avg_price = np.mean(close[-10:])
        roll_rel = (roll / avg_price) * 10000 # in pips-ish units
        
        # 2. Corwin-Schultz (Liquidity Depth)
        cs = calculate_corwin_schultz(high[-50:], low[-50:])
        cs_rel = cs * 10000 
        
        # 3. Score calculation
        # Lower spread = Higher score
        # Thresholds: < 5 pips = Great (90+), > 20 pips = Toxic (< 20)
        lq_score = 100 - (min(20, (roll_rel + cs_rel) / 2) * 4)
        
        return max(0, min(100, lq_score))
    except Exception as e:
        # print(f"[MICRO] Error calculating score: {e}")
        return 50.0 # Neutral fallback

if __name__ == "__main__":
    # Test with dummy data
    data = pd.DataFrame({
        'high': [1.01, 1.02, 1.015, 1.025, 1.03],
        'low':  [0.99, 0.995, 0.99, 1.0, 1.01],
        'close':[1.0, 1.01, 1.0, 1.015, 1.02]
    })
    score = get_microstructure_score(data)
    print(f"Microstructure Score (Dummy): {score:.2f}")
