"""
GitAgent v13.5 — MixTS: Thompson Sampling with Mixture Prior

Implements the regime-aware Thompson Sampling framework to replace static 
strategy weights with dynamic, learned posteriors across L regimes.

Mathematical Core:
1. Sample Regime Index: s ~ Categorical(P_t(s))
2. Sample Weights:     theta ~ N(mu_{t,s}, Sigma_{t,s})
3. Adaptive Update:    Sigma_{t+1,s} = (Sigma_0^{-1} + sigma^-2 * X X^T)^-1
                       mu_{t+1,s} = Sigma_{t+1,s}(Sigma_0^-1 * mu_0 + sigma^-2 * X * y)
"""

import numpy as np
import json
import os
import time

STATE_FILE = "C:\\Sentinel_Project\\mixts_state.json"
FEATURE_DIM = 13
FEATURE_KEYS = ['W_rsi', 'Wy_trend', 'S_struct', 'W_pctR', 'CMF_flow', 'COSMO_lunar', 'TFM_edge', 'TFM_dir', 'MEMORY_recall', 'MOE_bias', 'MOE_expert', 'SENT_pulse', 'SPEC_denoise']

class MixTSAgent:
    def __init__(self, L=4, dim=FEATURE_DIM, sigma_noise=1.0):
        self.L = L
        self.dim = dim
        self.sigma_noise = sigma_noise
        
        # Internal state
        self.regime_priors = np.ones(L) / L # P(s)
        self.regime_means = [np.zeros(dim) for _ in range(L)] # mu_s
        self.regime_covs = [np.eye(dim) * 0.05 for _ in range(L)] # Sigma_s
        
        # Original priors (Sigma_0, mu_0) for the Bayesian update math
        self.p0_means = [np.zeros(dim) for _ in range(L)]
        self.p0_cov_inv = [np.eye(dim) * (1.0/0.05) for _ in range(L)]
        
        # TimesNet Anomaly Tracking
        self.anomaly_buffer = []
        self.anomaly_mean = 0.0
        self.anomaly_std = 1.0
        
        self.load_state()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                
                self.regime_priors = np.array(data['priors'])
                # Failsafe normalization
                self.regime_priors /= (self.regime_priors.sum() + 1e-12)
                
                self.regime_means = [np.array(m) for m in data['means']]
                self.regime_covs = [np.array(c) for c in data['covs']]
                
                # Phase 161: Auto-expand for new features (e.g. 9 -> 11)
                for s in range(self.L):
                    if len(self.regime_means[s]) < self.dim:
                        pad_len = self.dim - len(self.regime_means[s])
                        self.regime_means[s] = np.pad(self.regime_means[s], (0, pad_len))
                        # Pad covariance diagonal with small priors
                        old_cov = self.regime_covs[s]
                        new_cov = np.eye(self.dim) * 0.05
                        new_cov[:old_cov.shape[0], :old_cov.shape[1]] = old_cov
                        self.regime_covs[s] = new_cov

                # Restore P0 state for updates
                self.p0_means = [np.array(m) for m in data.get('p0_means', [m.tolist() for m in self.regime_means])]
                # Handle p0 dimension mismatch
                for s in range(self.L):
                    if len(self.p0_means[s]) < self.dim:
                        self.p0_means[s] = self.regime_means[s].copy()
                
                self.p0_cov_inv = [np.linalg.inv(c + np.eye(self.dim)*1e-9) for c in self.regime_covs]
                
                print(f"[MIXTS] Loaded and synchronized state for L={self.L} / D={self.dim}.")
            except Exception as e:
                print(f"[MIXTS] Load error: {e}. Using defaults.")

    def save_state(self):
        state = {
            "priors": self.regime_priors.tolist(),
            "means": [m.tolist() for m in self.regime_means],
            "covs": [c.tolist() for c in self.regime_covs],
            "p0_means": [m.tolist() for m in self.p0_means],
            "p0_covs": [np.linalg.inv(ci).tolist() for ci in self.p0_cov_inv],
            "timestamp": time.time()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    def sample_regime_and_weights(self):
        """Thompson Sampling step."""
        # 1. Sample regime index s ~ P(s)
        self.regime_priors /= self.regime_priors.sum()
        s = np.random.choice(self.L, p=self.regime_priors)
        
        # 2. Sample weights theta ~ N(mu_s, Sigma_s)
        mu = self.regime_means[s].copy()
        
        # Phase 158: Bayesian Alpha Pruning
        # Dampen 'Wy_trend' (Idx 1) if expectation is negative
        if mu[1] < 0:
            mu[1] *= 0.5 
            
        # Boost 'S_struct' (SMC - Idx 2) as dominant alpha
        mu[2] *= 1.2
        
        cov = self.regime_covs[s]
        
        # Ensure covariance is positive definite for sampling
        cov_pd = cov + np.eye(self.dim) * 1e-9
        theta = np.random.multivariate_normal(mu, cov_pd)
        
        return int(s), theta.tolist(), self.regime_priors.tolist()

    def update_posteriors(self, x_vector, pnl_dollars):
        """
        Bayesian Update for ALL L regimes (Never waste data).
        x_vector: normalized feature values [dim]
        pnl_dollars: observed target value (e.g., net return or dollars)
        """
        X = np.array(x_vector).reshape(-1, 1)
        y = pnl_dollars
        sigma2_inv = 1.0 / (self.sigma_noise**2 + 1e-9)
        
        v_t = X @ X.T # Outer product
        b_t = X * y
        
        for s in range(self.L):
            # 1. Update Covariance: Sigma_{t+1,s} = (Sigma_0^{-1} + sigma^-2 * V_t)^-1
            new_cov_inv = self.p0_cov_inv[s] + sigma2_inv * v_t
            new_cov = np.linalg.inv(new_cov_inv + np.eye(self.dim) * 1e-9)
            
            # 2. Update Mean: mu_{t+1,s} = Sigma_{t+1,s}(Sigma_0^-1 * mu_0 + sigma^-2 * b_t)
            new_mean = new_cov @ (self.p0_cov_inv[s] @ self.p0_means[s].reshape(-1, 1) + sigma2_inv * b_t)
            
            self.regime_covs[s] = new_cov
            self.regime_means[s] = new_mean.flatten()
            
            # Update P0 trackers for next update (online learning)
            self.p0_cov_inv[s] = new_cov_inv
            self.p0_means[s] = self.regime_means[s]

        # 3. Update Regime Posterior P(s)
        # Based on how well the observed (x, y) fits each regime's model
        likelihoods = []
        for s in range(self.L):
            # Probability of observing y given x and current regime s model
            pred_y = np.dot(self.regime_means[s], x_vector)
            error = y - pred_y
            # Log-likelihood (Gaussian)
            ll = -0.5 * (error**2 / (self.sigma_noise**2 + 1e-9))
            likelihoods.append(np.exp(ll))
        
        likelihoods = np.array(likelihoods)
        new_priors = self.regime_priors * likelihoods
        sum_priors = np.sum(new_priors)
        
        if sum_priors > 1e-12:
            self.regime_priors = new_priors / sum_priors
        else:
            # Failsafe: reset to uniform if likelihoods collapse
            self.regime_priors = np.ones(self.L) / self.L
            
        # Final precision normalization for np.random.choice
        self.regime_priors /= self.regime_priors.sum()
            
        self.save_state()
        return self.regime_priors.tolist()

    def inject_entropy(self, anomaly_score):
        """
        Phase 17: Spectral Entropy Injection.
        Increases exploration when TimesNet detects a reconstruction anomaly.
        """
        # Update rolling stats
        self.anomaly_buffer.append(anomaly_score)
        if len(self.anomaly_buffer) > 50:
            self.anomaly_buffer.pop(0)
            self.anomaly_mean = np.mean(self.anomaly_buffer)
            self.anomaly_std = np.std(self.anomaly_buffer) + 1e-9
            
        # Transition Detection: 2.0 sigma above rolling mean
        if anomaly_score > (self.anomaly_mean + 2.0 * self.anomaly_std):
            print(f"[MIXTS] SPECTRAL ANOMALY DETECTED (Score: {anomaly_score:.4f}). Injecting entropy.")
            # Multiply toward uniform: push every probability closer to 1/L
            uniform = np.ones(self.L) / self.L
            alpha = 0.5 # 50% shift toward uniform
            self.regime_priors = (1 - alpha) * self.regime_priors + alpha * uniform
            self.regime_priors /= self.regime_priors.sum()
            return True
        return False

def get_mixts_weights():
    """Singleton helper for easy main loop integration."""
    agent = MixTSAgent()
    s, theta, priors = agent.sample_regime_and_weights()
    return s, theta, priors

if __name__ == "__main__":
    # Self-test code
    agent = MixTSAgent()
    print("Initial Regime Priors:", agent.regime_priors)
    
    test_x = [0.5, 0.2, -0.1, 0.8, -0.3, 0.0, 0.4, 0.4, 0.5]
    test_y = 10.5 # Strong positive outcome
    
    s, theta, priors = agent.sample_regime_and_weights()
    print(f"Sampled Regime: {s}, Weights (first 3): {theta[:3]}")
    
    new_priors = agent.update_posteriors(test_x, test_y)
    print("New Regime Priors:", new_priors)
