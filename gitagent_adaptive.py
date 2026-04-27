import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression

def hurst_exponent(returns):
    """
    Hurst Exponent (Rescaled Range Method).
    H > 0.5: Trending, H < 0.5: Mean-reverting, H ≈ 0.5: Random Walk.
    """
    n = len(returns)
    if n < 30: return {"H": 0.5, "regime": "RANDOM", "tradable": False, "trend_boost": 1.0, "mr_boost": 1.0}

    # Sizes for R/S calculation
    sizes = [10, 15, 20, 30, 40]
    sizes = [s for s in sizes if s <= n // 2]
    
    if len(sizes) < 2:
         return {"H": 0.5, "regime": "RANDOM", "tradable": False, "trend_boost": 1.0, "mr_boost": 1.0}

    log_n = []
    log_rs = []

    for size in sizes:
        num_blocks = n // size
        rs_list = []
        for b in range(num_blocks):
            block = returns[b*size : (b+1)*size]
            mean = np.mean(block)
            deviations = block - mean
            cum_dev = np.cumsum(deviations)
            R = np.max(cum_dev) - np.min(cum_dev)
            S = np.std(block)
            if S > 0:
                rs_list.append(R / S)
        
        if len(rs_list) > 0:
            log_n.append(np.log(size))
            log_rs.append(np.log(np.mean(rs_list)))

    if len(log_n) < 2:
         return {"H": 0.5, "regime": "RANDOM", "tradable": False, "trend_boost": 1.0, "mr_boost": 1.0}

    # Linear Regression to find H
    H, _, _, _, _ = stats.linregress(log_n, log_rs)
    H = np.clip(H, 0.01, 0.99)
    
    regime = "TRENDING" if H > 0.6 else "MEAN_REV" if H < 0.4 else "RANDOM"
    tradable = abs(H - 0.5) > 0.08
    
    trend_boost = 1.0 + (H - 0.55) * 2 if H > 0.55 else 0.7 if H < 0.45 else 1.0
    mr_boost = 1.0 + (0.45 - H) * 2 if H < 0.45 else 0.7 if H > 0.55 else 1.0
    
    return {
        "H": round(H, 3), 
        "regime": regime, 
        "tradable": tradable, 
        "trend_boost": trend_boost, 
        "mr_boost": mr_boost
    }

def ising_herding(returns, rsi, sentiment):
    """
    Ising Model - Herding Detector.
    Returns Magnetization (M) and Susceptibility (chi).
    """
    n = len(returns)
    if n < 10: return {"magnetization": 0, "chi": 0, "phase": "BALANCED", "contrarian": 0.0}
    
    # Spins: +1 for up, -1 for down
    spins = np.where(returns > 0, 1, -1)
    
    # Raw Magnetization (Alignment)
    M_raw = abs(np.sum(spins)) / n
    
    # Field factors (sentiment/rsi extremes)
    sent_factor = 1.15 if abs(sentiment) > 0.3 else 1.0
    rsi_factor = 1.15 if rsi > 75 or rsi < 25 else 1.0
    
    M = min(1.0, M_raw * sent_factor * rsi_factor)
    
    # Susceptibility (variance of magnetization in windows)
    win = 5
    m_wins = [abs(np.sum(spins[i:i+win])) / win for i in range(n - win + 1)]
    chi = np.var(m_wins) if len(m_wins) > 1 else 0
    
    phase = "BALANCED"
    contrarian = 0.0
    
    if M > 0.8:
        phase = "EXTREME_HERD"
        herd_dir = 1 if np.sum(spins[-5:]) > 0 else -1
        contrarian = -herd_dir * 0.3
    elif M > 0.6:
        phase = "MODERATE_HERD"
        herd_dir = 1 if np.sum(spins[-5:]) > 0 else -1
        contrarian = -herd_dir * 0.1
    elif chi > 0.15:
        phase = "CRITICAL"
        
    return {
        "magnetization": round(M, 3), 
        "chi": round(chi, 4), 
        "phase": phase, 
        "contrarian": contrarian
    }

def fractal_dimension(prices):
    """
    Higuchi Fractal Dimension (Complexity analysis).
    D=1 (Smooth), D=2 (Chaotic).
    """
    n = len(prices)
    if n < 20: return {"D": 1.5, "roughness": "MODERATE", "modifier": 1.0}
    
    k_max = min(8, n // 4)
    log_k = []
    log_l = []
    
    for k in range(1, k_max + 1):
        l_k = []
        for m in range(k):
            indices = np.arange(m, n, k)
            if len(indices) < 2: continue
            
            # Simplified path length
            length = np.sum(np.abs(np.diff(prices[indices])))
            norm_factor = (n - 1) / (len(indices) * k)
            l_k.append(length * norm_factor / k)
            
        if len(l_k) > 0:
            log_k.append(np.log(1.0/k))
            log_l.append(np.log(np.mean(l_k)))
            
    if len(log_k) < 2:
        return {"D": 1.5, "roughness": "MODERATE", "modifier": 1.0}
        
    D, _, _, _, _ = stats.linregress(log_k, log_l)
    D = np.clip(D, 1.0, 2.0)
    
    roughness = "SMOOTH" if D < 1.2 else "MILD" if D < 1.4 else "MODERATE" if D < 1.6 else "CHAOTIC"
    modifier = 1.1 if D < 1.2 else 1.0 if D < 1.4 else 0.9 if D < 1.6 else 0.7
    
    return {"D": round(D, 3), "roughness": roughness, "modifier": modifier}

def first_passage_probability(price, tp, sl, mu, sigma, sigma_forecast):
    """
    Fokker-Planck absorption boundary solution for P(TP hit before SL hit).
    Enhanced with numerical stability checks for exponents.
    """
    d_upper = tp - price
    d_lower = price - sl
    
    if d_upper <= 0 or d_lower <= 0: return 0.5
    
    sigma2 = max(1e-10, sigma**2)
    
    # If drift is extremely small, use Pure Diffusion limit
    if abs(mu) < 1e-9:
        p_tp = d_lower / (d_lower + d_upper)
    else:
        # Fokker-Planck exact solution: p_tp = (1 - exp(-2*mu*L/sigma2)) / (1 - exp(-2*mu*(L+U)/sigma2))
        try:
            arg_lower = -2 * mu * d_lower / sigma2
            arg_total = -2 * mu * (d_lower + d_upper) / sigma2
            
            # Numerical safety: if exponents blow up, use the limit
            if arg_total > 500: # Exponent too large, denom will be huge negative
                p_tp = 1.0 if mu > 0 else 0.0
            elif arg_total < -500: # Exponent too small, term becomes 0
                p_tp = 1.0 if mu > 0 else 0.0
            else:
                exp_lower = np.exp(arg_lower)
                exp_total = np.exp(arg_total)
                denom = 1 - exp_total
                if abs(denom) < 1e-10:
                    p_tp = d_lower / (d_lower + d_upper) # Tail-call to diffusion
                else:
                    p_tp = (1 - exp_lower) / denom
        except Exception:
            p_tp = d_lower / (d_lower + d_upper)
            
    # Naive NaN check
    if np.isnan(p_tp):
        p_tp = d_lower / (d_lower + d_upper)

    # Volatility uncertainty dampener (Path Integral proxy)
    vol_ratio = sigma_forecast / max(0.001, sigma)
    path_adjust = 1.0 / (1.0 + 0.3 * abs(vol_ratio - 1))
    
    p_tp_final = p_tp * path_adjust + 0.5 * (1.0 - path_adjust)
    return np.clip(p_tp_final, 0.01, 0.99)

def meta_label_gate(p_tp, snr_grade, hurst_tradable, herding_phase, sig_quality, fractal_mod):
    """
    Decision gate: Should we EXECUTE or SKIP?
    Returns meta_score (0-6) and final decision.
    """
    score = 0.0
    
    # 1. First Passage Edge (tuned for M15 data where drift is near-zero)
    if p_tp > 0.60: score += 1.5
    elif p_tp > 0.52: score += 1.0
    elif p_tp > 0.48: score += 0.5
    elif p_tp > 0.45: score += 0.3  # M15 drift is near-zero, 0.45-0.48 is normal
    
    # 2. SNR Grade
    if snr_grade in ["A", "B"]: score += 1.0
    elif snr_grade == "C": score += 0.5
    
    # 3. Hurst Tradability
    if hurst_tradable: score += 1.0
    else: score += 0.2
    
    # 4. Ising Phase
    if herding_phase == "BALANCED": score += 0.8
    elif herding_phase == "MODERATE_HERD": score += 0.5
    elif herding_phase == "EXTREME_HERD": score += 0.7
    
    # 5. Signal Quality (v7.1)
    if sig_quality > 1.05: score += 1.0
    elif sig_quality > 0.95: score += 0.5
    elif sig_quality > 0.85: score += 0.3  # Don't zero out for decent quality
    
    # 6. Fractal Complexity
    score += max(0, (fractal_mod - 0.7) * 2)
    
    decision = "EXECUTE" if score >= 2.5 else "SKIP"
    return score, decision

def cpcv_reliability(returns, signal, hurst_val, alpha_val):
    """
    Combinatorial Purged Cross-Validation proxy.
    Checks for backtest overfitting and consistency across 5 folds.
    """
    n = len(returns)
    if n < 40: return 0.5, "C"
    
    K = 5
    fold_size = n // K
    correct = 0
    
    for k in range(K):
        test_start = k * fold_size
        test_end = (k + 1) * fold_size
        
        test_rets = returns[test_start:test_end]
        test_avg = np.mean(test_rets)
        
        # Check if current direction worked in this historic fold
        if (signal == "BUY" and test_avg > 0) or (signal == "SELL" and test_avg < 0):
            correct += 1
            
    cv_score = correct / K
    
    # Overfit penalty based on Hurst (random walk) and Alpha (instability)
    pbo = (1.0 - cv_score)
    if abs(hurst_val - 0.5) < 0.1: pbo += 0.3
    if alpha_val < 1.6: pbo += 0.1
    
    grade = "A" if cv_score >= 0.8 and pbo < 0.4 else "B" if cv_score >= 0.6 else "C" if cv_score >= 0.4 else "F"
    
    return cv_score, grade

def get_smc_bias(df):
    """
    SMC/ICT Structure Bias: returns -1/0/1 based on SMA50 trend + RSI exhaustion.
    """
    if len(df) < 50: return 0
    price = df['close'].iloc[-1]
    sma50 = df['close'].rolling(50).mean().iloc[-1]
    
    # RSI for exhaustion
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    if price > sma50 and rsi < 40: return 1  # Buy: Trend UP + Deep Discount
    if price < sma50 and rsi > 60: return -1 # Sell: Trend DOWN + Premium Premium
    return 0

def get_whale_bias(df):
    """
    Whale Tracking: returns -1/0/1 based on Volume Spikes + Price Action.
    """
    if len(df) < 20: return 0
    vol = df['tick_volume'].iloc[-1]
    vol_sma = df['tick_volume'].rolling(20).mean().iloc[-1]
    vol_ratio = vol / (vol_sma + 1e-9)
    
    if vol_ratio > 2.0:
        if df['close'].iloc[-1] > df['close'].iloc[-2]: return 1
        if df['close'].iloc[-1] < df['close'].iloc[-2]: return -1
    return 0

def fit_trend_channel(prices, n_std=2.0):
    """
    Fits a Linear Regression Trend Channel to the price data.
    Returns: slope, intercept, upper_bound, lower_bound, current_pos_in_channel
    """
    n = len(prices)
    if n < 20:
        return 0, prices[-1], prices[-1], prices[-1], 0.5
        
    x = np.arange(n).reshape(-1, 1)
    y = prices.reshape(-1, 1)
    
    model = LinearRegression()
    model.fit(x, y)
    
    y_pred = model.predict(x)
    residuals = y - y_pred
    std_dev = np.std(residuals)
    
    slope = float(model.coef_[0][0])
    intercept = float(model.intercept_[0])
    
    current_pred = y_pred[-1][0]
    upper = current_pred + (n_std * std_dev)
    lower = current_pred - (n_std * std_dev)
    
    # Position in channel: 0 (bottom) to 1 (top)
    width = (upper - lower) + 1e-9
    pos = (prices[-1] - lower) / width
    
    return slope, current_pred, upper, lower, np.clip(pos, 0, 1)
