"""
GitAgent v13.5 — MixTS Prior Bootstrapper

Performs offline GMM fitting on historical trade data to derive P0 priors
for the MixTS framework. 

Steps:
1. Load rsi_trade_dataset.json
2. Segment trades into chronological periods (N=20)
3. For each period, solve for optimal weight vector theta (Ridge regression)
4. Fit a 4-component GMM to the resulting {theta} vectors using custom EM.
5. Export to mixts_state.json.
"""

import json
import numpy as np
import os
from scipy import stats

DATASET_FILE = "C:\\Sentinel_Project\\rsi_trade_dataset.json"
STATE_FILE = "C:\\Sentinel_Project\\mixts_state.json"
FEATURE_KEYS = ['W_rsi', 'Wy_trend', 'S_struct', 'W_pctR', 'CMF_flow', 'COSMO_lunar', 'TFM_edge', 'TFM_dir', 'MEMORY_recall']
PERIOD_SIZE = 25 # Number of trades per regime sample
L_REGIMES = 4

def solve_optimal_theta(X, y, alpha=0.1):
    """Simple Ridge regression to find optimal theta for a period."""
    # X: [N, dim], y: [N]
    dim = X.shape[1]
    XtX = X.T @ X + alpha * np.eye(dim)
    Xty = X.T @ y
    return np.linalg.inv(XtX) @ Xty

def gmm_em(data, L, iterations=50):
    """Custom EM implementation for GMM in pure numpy/scipy."""
    N, D = data.shape
    
    # Initialize components
    pi = np.ones(L) / L
    means = data[np.random.choice(N, L, replace=False)]
    covs = [np.eye(D) * 0.1 for _ in range(L)]
    
    for _ in range(iterations):
        # --- E-Step: Responsibilities ---
        resp = np.zeros((N, L))
        for s in range(L):
            try:
                # Use multivariate_normal for logpdf stability
                rv = stats.multivariate_normal(means[s], covs[s], allow_singular=True)
                resp[:, s] = pi[s] * rv.pdf(data)
            except:
                resp[:, s] = 1e-9
        
        sum_resp = resp.sum(axis=1, keepdims=True) + 1e-12
        resp /= sum_resp
        
        # --- M-Step: Parameters ---
        Nk = resp.sum(axis=0)
        pi = Nk / (Nk.sum() + 1e-12)
        for s in range(L):
            if Nk[s] > 1e-3:
                means[s] = (resp[:, s:s+1] * data).sum(axis=0) / Nk[s]
                diff = data - means[s]
                covs[s] = (resp[:, s:s+1] * diff).T @ diff / Nk[s]
                
                # ENFORCE CONSTRAINT: lambda_max < 0.1
                # We do this by regularizing the covariance matrix
                covs[s] += np.eye(D) * 1e-6
                vals, vecs = np.linalg.eigh(covs[s])
                if np.max(vals) > 0.1:
                    scaling = 0.09 / np.max(vals)
                    covs[s] = (vecs * (vals * scaling)) @ vecs.T
            else:
                # Component vanished, reset to random
                means[s] = data[np.random.choice(N)]
                covs[s] = np.eye(D) * 0.05
    
    # Final normalization safety
    pi = pi / pi.sum()
    return pi, means, covs

def bootstrap():
    if not os.path.exists(DATASET_FILE):
        print("[BOOTSTRAP] Error: Dataset not found.")
        return
    
    with open(DATASET_FILE, 'r') as f:
        data = json.load(f)
    
    trades = data.get('trades', [])
    print(f"[BOOTSTRAP] Loaded {len(trades)} historical trades.")
    
    thetas = []
    for i in range(0, len(trades) - PERIOD_SIZE, 5): # Sliding window
        batch = trades[i : i + PERIOD_SIZE]
        X_list = []
        y_list = []
        for t in batch:
            f = t.get('features', {})
            # Map features to vector
            vec = [f.get(k, 0.0) for k in FEATURE_KEYS]
            # Fill missing with 0
            vec = [v if v is not None else 0.0 for v in vec]
            X_list.append(vec)
            y_list.append(t.get('pnl', 0.0))
        
        X = np.array(X_list)
        y = np.array(y_list)
        thetas.append(solve_optimal_theta(X, y))
    
    theta_matrix = np.array(thetas)
    print(f"[BOOTSTRAP] Derived {len(thetas)} optimal parameter samples.")
    
    # Fit GMM
    print(f"[BOOTSTRAP] Fitting {L_REGIMES}-regime GMM...")
    pi, means, covs = gmm_em(theta_matrix, L_REGIMES)
    
    # Verify constraint
    for s in range(L_REGIMES):
        vals = np.linalg.eigvals(covs[s])
        print(f"Regime {s} Max Eigenvalue: {np.max(vals).real:.5f}")
    
    # Save State
    state = {
        "priors": pi.tolist(),
        "means": [m.tolist() for m in means],
        "covs": [c.tolist() for c in covs],
        "p0_means": [m.tolist() for m in means],
        "p0_covs": [c.tolist() for c in covs],
        "feature_keys": FEATURE_KEYS,
        "timestamp": os.path.getmtime(DATASET_FILE)
    }
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    print(f"[BOOTSTRAP] MixTS Prior state saved to {STATE_FILE}")

if __name__ == "__main__":
    bootstrap()
