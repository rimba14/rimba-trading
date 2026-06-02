"""
GitAgent v6.0 — HMM Market State Filter
Inspired by Jim Simons / Renaissance Technologies Medallion Fund methodology.

Uses a Hidden Markov Model (Baum-Welch) to detect the current hidden market state
for each asset from its own price history — no external index required.

HIDDEN STATES (learned, not hardcoded):
  State 0 = BULL  (trending up, buy bias)
  State 1 = BEAR  (trending down, sell bias)
  State 2 = RANGE (sideways/choppy, reduce size, wait)

OBSERVATIONS (discretized daily returns — 5 bins):
  0 = STRONG UP  (> +1.5%)
  1 = WEAK UP    (+0.3% to +1.5%)
  2 = FLAT       (-0.3% to +0.3%)
  3 = WEAK DOWN  (-1.5% to -0.3%)
  4 = STRONG DOWN (< -1.5%)

Per-axis regime adjustments:
  BULL  → lower confidence threshold by 5% (be more aggressive)
  BEAR  → lower confidence threshold by 5% on SELL (be more aggressive short)
  RANGE → raise confidence threshold by 10% (be more selective)
"""

import numpy as np

N_STATES = 3       # BULL, BEAR, RANGE
N_OBS    = 5       # 5 return bins
MAX_ITER = 50      # Baum-Welch iterations
TOL      = 1e-4    # Convergence threshold

STATE_NAMES = {0: "BULL", 1: "BEAR", 2: "RANGE"}

# Thresholds for discretising daily % returns into observation bins
OBS_THRESHOLDS = [-1.5, -0.3, 0.3, 1.5]  # Boundaries between bins

def discretise(returns: np.ndarray) -> np.ndarray:
    """Convert a series of daily % returns into integer observation indices."""
    return 4 - np.digitize(returns, OBS_THRESHOLDS)

def _forward(obs, A, B, pi):
    T = len(obs)
    N = A.shape[0]
    alpha = np.zeros((T, N))
    alpha[0] = pi * B[:, obs[0]]
    for t in range(1, T):
        alpha[t] = (alpha[t-1] @ A) * B[:, obs[t]]
        s = alpha[t].sum()
        if s > 0:
            alpha[t] /= s
    return alpha

def _backward(obs, A, B):
    T = len(obs)
    N = A.shape[0]
    beta = np.zeros((T, N))
    beta[-1] = 1.0
    for t in range(T-2, -1, -1):
        beta[t] = A @ (B[:, obs[t+1]] * beta[t+1])
        s = beta[t].sum()
        if s > 0:
            beta[t] /= s
    return beta

def baum_welch(obs: np.ndarray, n_states: int = N_STATES, n_obs: int = N_OBS,
               max_iter: int = MAX_ITER, tol: float = TOL):
    """
    Train an HMM on a sequence of discrete observations using Baum-Welch.
    Returns (A, B, pi) — transition matrix, emission matrix, initial probs.
    """
    # Random initialisation (with reproducible seed per symbol via obs hash)
    rng = np.random.default_rng(int(np.sum(obs[:10])) % 2**31)
    A  = rng.dirichlet(np.ones(n_states), size=n_states)
    B  = rng.dirichlet(np.ones(n_obs),    size=n_states)
    pi = rng.dirichlet(np.ones(n_states))

    T = len(obs)
    prev_log_lik = -np.inf

    for _ in range(max_iter):
        # E-step
        alpha = _forward(obs, A, B, pi)
        beta  = _backward(obs, A, B)

        gamma = alpha * beta
        gamma_sum = gamma.sum(axis=1, keepdims=True)
        gamma_sum = np.where(gamma_sum == 0, 1e-10, gamma_sum)
        gamma /= gamma_sum

        xi = np.zeros((T-1, n_states, n_states))
        for t in range(T-1):
            denom = 0.0
            for i in range(n_states):
                for j in range(n_states):
                    xi[t, i, j] = alpha[t, i] * A[i, j] * B[j, obs[t+1]] * beta[t+1, j]
                    denom += xi[t, i, j]
            if denom > 0:
                xi[t] /= denom

        # M-step
        pi = gamma[0]
        A  = xi.sum(axis=0) / (gamma[:-1].sum(axis=0, keepdims=True).T + 1e-10)
        A  = A / A.sum(axis=1, keepdims=True)

        B_new = np.zeros_like(B)
        for o in range(n_obs):
            B_new[:, o] = gamma[obs == o].sum(axis=0)
        B_new /= (gamma.sum(axis=0, keepdims=True).T + 1e-10)
        B = B_new / B_new.sum(axis=1, keepdims=True)

        # Convergence check
        log_lik = np.log(alpha[-1].sum() + 1e-10)
        if abs(log_lik - prev_log_lik) < tol:
            break
        prev_log_lik = log_lik

    return A, B, pi

def discretise_cp(cp_probs: np.ndarray) -> np.ndarray:
    """Convert change-point probabilities [0.0, 1.0] to discrete binary bins."""
    return np.where(cp_probs >= 0.5, 1, 0)

def label_states(A: np.ndarray, B: np.ndarray) -> dict:
    """
    Auto-label hidden states as BULL / BEAR / RANGE based on
    each state's emission distribution (which returns it favours).
    """
    # Expected return for each state (positive obs = STRONG/WEAK UP)
    # Weights: STRONG_UP=+2, WEAK_UP=+1, FLAT=0, WEAK_DOWN=-1, STRONG_DOWN=-2
    ret_weights = np.array([2, 1, 0, -1, -2])
    
    # If B has 10 columns, we marginalize over the change-point variable
    if B.shape[1] == 10:
        B_marginal = B[:, :5] + B[:, 5:]
        expected_ret = B_marginal @ ret_weights
    else:
        expected_ret = B @ ret_weights  # shape (n_states,)

    # Sort states by expected return descending
    order = np.argsort(expected_ret)[::-1]
    labels = {}
    label_names = ["BULL", "RANGE", "BEAR"] if N_STATES == 3 else ["BULL", "BEAR"]
    for rank, state_idx in enumerate(order):
        labels[int(state_idx)] = label_names[min(rank, len(label_names)-1)]
    return labels

def get_current_state(price_series: np.ndarray, lookback: int = 200, cp_probs: np.ndarray = None):
    """
    Given a numpy array of daily closing prices, train an HMM and return
    the most likely current hidden state label, probability, and condition number.

    Returns:
        state_label (str): "BULL", "BEAR", or "RANGE"
        state_prob  (float): probability of being in that state (0–1)
        all_probs   (dict): {label: probability, "regime_condition_number": cond_num}
    """
    if len(price_series) < 60:
        return "RANGE", 0.5, {"BULL": 0.33, "BEAR": 0.33, "RANGE": 0.34, "regime_condition_number": 1.0}

    # Use last `lookback` bars
    prices = price_series[-lookback:]
    returns = np.diff(prices) / prices[:-1] * 100  # daily % returns

    obs_returns = discretise(returns)
    
    if cp_probs is not None:
        # Align cp_probs to match returns length (len(prices) - 1)
        cp_subset = cp_probs[-len(returns):]
        if len(cp_subset) < len(returns):
            cp_subset = np.pad(cp_subset, (len(returns) - len(cp_subset), 0), 'constant')
        else:
            cp_subset = cp_subset[-len(returns):]
        obs_cp = discretise_cp(cp_subset)
        # Joint observations (size 10)
        obs = obs_returns + 5 * obs_cp
        n_obs_dims = 10
    else:
        obs = obs_returns
        n_obs_dims = 5

    try:
        A, B, pi = baum_welch(obs, n_states=3, n_obs=n_obs_dims)
        # Calculate transition matrix condition number κ(P) = ||P|| * ||P^-1||
        cond_num = float(np.linalg.cond(A, p=2))
        if np.isnan(cond_num) or np.isinf(cond_num):
            cond_num = 99.0
    except Exception:
        # Safely default to 99.0 to trigger risk warning / entry clamp
        return "RANGE", 0.5, {"BULL": 0.33, "BEAR": 0.33, "RANGE": 0.34, "regime_condition_number": 99.0}

    # Get current state probabilities from forward pass
    alpha = _forward(obs, A, B, pi)
    current_probs = alpha[-1]
    current_probs /= (current_probs.sum() + 1e-10)

    state_labels = label_states(A, B)

    # Build label → prob mapping
    label_probs = {}
    for state_idx, label in state_labels.items():
        label_probs[label] = float(current_probs[state_idx])

    # Fill missing labels with 0
    for lbl in ["BULL", "BEAR", "RANGE"]:
        if lbl not in label_probs:
            label_probs[lbl] = 0.0

    # Expose the condition number inside label_probs dictionary
    label_probs["regime_condition_number"] = cond_num

    best_state_idx = int(np.argmax(current_probs))
    best_label = state_labels[best_state_idx]
    best_prob  = float(current_probs[best_state_idx])

    return best_label, best_prob, label_probs

def hmm_regime_adjustment(state_label: str, sig: str, agent_name: str = "") -> tuple:
    """
    Given an HMM state and the current swarm signal direction,
    return (conf_adjust, size_adjust).

    conf_adjust: added to REGIME_CONF_THRESHOLD (negative = more permissive)
    size_adjust: multiplied into REGIME_SIZE_MULT
    """
    if state_label == "RANGE":
        if agent_name.upper() in ["VPIN", "HAWKES"]:
            return +999.0, 0.0  # Completely suppress noise-sensitive signals

    if state_label == "BULL":
        if sig == "BUY":
            return -5.0, 1.10   # Lower bar + 10% bigger for aligned BUYs
        elif sig == "SELL":
            return +8.0, 0.75   # Raise bar + smaller size for counter-trend SELLs
        else:
            return 0.0, 1.0

    elif state_label == "BEAR":
        if sig == "SELL":
            return -5.0, 1.10   # Lower bar + 10% bigger for aligned SELLs
        elif sig == "BUY":
            return +8.0, 0.75   # Raise bar + smaller size for counter-trend BUYs
        else:
            return 0.0, 1.0

    else:  # RANGE
        return +10.0, 0.80      # Raise bar + smaller size in choppy markets


if __name__ == "__main__":
    # Quick test with synthetic data
    print("Testing HMM State Filter with Condition Number...")
    np.random.seed(42)
    # Simulate a bull run then a crash
    bull_prices  = 100 * np.cumprod(1 + np.random.normal(0.003, 0.01, 100))
    bear_prices  = bull_prices[-1] * np.cumprod(1 + np.random.normal(-0.005, 0.015, 50))
    range_prices = bear_prices[-1] * np.cumprod(1 + np.random.normal(0.0, 0.008, 50))
    prices = np.concatenate([bull_prices, bear_prices, range_prices])

    label, prob, all_probs = get_current_state(prices)
    print(f"Current HMM State: {label} ({prob*100:.1f}%)")
    print(f"All States: {all_probs}")
    print("HMM module OK.")
