import numpy as np
from scipy import stats

def levy_alpha(returns):
    """
    McCulloch quantile estimator for alpha (stability index).
    alpha=2 is Gaussian, alpha<2 is fat-tailed.
    """
    if len(returns) < 20: return 2.0
    sorted_ret = np.sort(returns)
    n = len(sorted_ret)
    
    def q(p):
        return sorted_ret[int(p * n)]

    q95, q05 = q(0.95), q(0.05)
    q75, q25 = q(0.75), q(0.25)
    iqr = q75 - q25
    
    if iqr < 1e-10: return 2.0
    nu = (q95 - q05) / iqr
    
    # nu approx 2.44 -> alpha=2 (Gaussian)
    # nu approx 4.0 -> alpha=1.5
    alpha = 2.0 - (nu - 2.44) * 0.32
    return np.clip(alpha, 1.1, 2.0)

def levy_scale(returns, alpha):
    """
    Gamma (scale) parameter for Levy stable distribution.
    """
    if len(returns) < 10: return 0.01
    sorted_ret = np.sort(returns)
    n = len(sorted_ret)
    q75 = sorted_ret[int(0.75 * n)]
    q25 = sorted_ret[int(0.25 * n)]
    iqr = q75 - q25
    
    denom = 1.35 * np.sqrt(alpha / 2.0)
    return max(1e-6, iqr / max(1e-10, denom))

def levy_es(alpha, gamma, confidence=0.95):
    """
    Expected Shortfall (ES) for Levy stable distribution.
    """
    # VaR_p approx gamma * (c_alpha / (1-p))^(1/alpha)
    c_alpha = (np.pi * alpha / 2.0)**(1.0 / alpha)
    tail = 1.0 - confidence
    var_p = gamma * c_alpha * (1.0 / tail)**(1.0 / alpha)
    
    # ES = VaR * alpha / (alpha - 1)
    es_multiplier = alpha / (alpha - 1.0) if alpha > 1.01 else 10.0
    return var_p * es_multiplier

def kl_divergence(current_returns, historical_returns, bins=20):
    """
    Kullback-Leibler Divergence between current and historical return distributions.
    """
    if len(current_returns) < 10 or len(historical_returns) < 10: return 0.0
    
    mn = min(np.min(current_returns), np.min(historical_returns))
    mx = max(np.max(current_returns), np.max(historical_returns))
    
    p_counts, edges = np.histogram(current_returns, bins=bins, range=(mn, mx))
    q_counts, _ = np.histogram(historical_returns, bins=bins, range=(mn, mx))
    
    epsilon = 1e-10
    p = (p_counts + epsilon) / (len(current_returns) + bins * epsilon)
    q = (q_counts + epsilon) / (len(historical_returns) + bins * epsilon)
    
    return np.sum(p * np.log(p / q))

def transfer_entropy(source, target, lag=1):
    """
    Directional causal information flow from source to target.
    """
    if len(source) < 20 or len(target) < 20: return 0.0
    
    # Discretize: -1, 0, 1
    def discretize(arr):
        return np.where(arr > 0.002, 1, np.where(arr < -0.002, -1, 0))
    
    s = discretize(source[:-lag])
    t_curr = discretize(target[lag:])
    t_past = discretize(target[:-lag])
    
    n = len(s)
    
    # Joint P(T_next, T_past, S_past)
    joint_counts = {}
    m_tp_sp = {} # P(T_past, S_past)
    m_tn_tp = {} # P(T_next, T_past)
    m_tp = {}    # P(T_past)
    
    for i in range(n):
        k3 = (t_curr[i], t_past[i], s[i])
        k2_tp_sp = (t_past[i], s[i])
        k2_tn_tp = (t_curr[i], t_past[i])
        k1_tp = t_past[i]
        
        joint_counts[k3] = joint_counts.get(k3, 0) + 1
        m_tp_sp[k2_tp_sp] = m_tp_sp.get(k2_tp_sp, 0) + 1
        m_tn_tp[k2_tn_tp] = m_tn_tp.get(k2_tn_tp, 0) + 1
        m_tp[k1_tp] = m_tp.get(k1_tp, 0) + 1
        
    te = 0.0
    for k, c in joint_counts.items():
        tn, tp, sp = k
        p3 = c / n
        p_tn_given_tp_sp = c / m_tp_sp[(tp, sp)]
        p_tn_given_tp = m_tn_tp[(tn, tp)] / m_tp[tp]
        
        if p_tn_given_tp > 0:
            te += p3 * np.log(p_tn_given_tp_sp / p_tn_given_tp)
            
    return max(0.0, te)

def thermodynamic_temperature(alpha, kl_div, persistence, vix):
    """
    Calculates the 'System Temperature' (System Turbulence).
    T=1 is stable, T>2 is chaotic.
    """
    levy_heat = (2.0 - alpha) / max(0.1, alpha)
    regime_heat = kl_div
    vol_heat = persistence
    vix_heat = max(0, (vix - 15) / 30.0)
    
    return 1.0 + 1.5 * levy_heat + 2.0 * regime_heat + 1.0 * vol_heat + 0.5 * vix_heat

def volatility_clustering(returns):
    """
    GARCH-style persistence measurement (autocorrelation of squared returns).
    """
    if len(returns) < 10: return 0.5
    sq_ret = returns**2
    avg_sq = np.mean(sq_ret)
    
    # Autocorrelation lag 1
    if np.std(sq_ret) < 1e-10: return 0.0
    ac = np.corrcoef(sq_ret[1:], sq_ret[:-1])[0, 1]
    
    persistence = np.clip(0.5 + ac * 0.5, 0.0, 1.0)
    return persistence

def entropy_flux_ratio(ret_ann, alpha, gamma, kl_div, persistence):
    """
    Bouchaud's replacement for the Sharpe ratio.
    Return / (Scale * Tail Penalty * Regime Penalty * Cluster Penalty)
    """
    tail_factor = (2.0 - alpha) / max(0.1, alpha)
    regime_factor = 1.0 + kl_div
    cluster_factor = np.sqrt(max(0.01, persistence))
    
    entropy_flux = gamma * tail_factor * regime_factor * cluster_factor
    if entropy_flux < 1e-6: return 99.0 if ret_ann > 0 else -99.0
    
    return ret_ann / entropy_flux
