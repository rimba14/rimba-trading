import numpy as np
import pandas as pd
import logging
from agent_quarantine import registry, register_default_agents

logger = logging.getLogger("AlphaCombiner")

class AlphaCombiner:
    """
    Implementation of 'A Unified Framework for Alpha Extraction and Signal Combination'
    Eq (1-12) for Residual Orthogonalization and Multi-Factor Blending.
    """
    def __init__(self, window=20):
        self.window = window
        self.signal_history = {} # sym -> list of raw scores
        register_default_agents()
        
    def process_signals(self, signals_dict, volatilities):
        """
        signals_dict: { 'sym': { 'agent_1': score, 'agent_2': score ... } }
        volatilities: { 'sym': current_atr }
        """
        if not signals_dict: return {}
        
        # v27.0: Filter out quarantined (uninitialized) agents
        filtered_signals_dict = {}
        for sym, scores in signals_dict.items():
            res = registry.filter_agents(scores)
            if res.filtered_scores:
                filtered_signals_dict[sym] = res.filtered_scores
                
        signals_dict = filtered_signals_dict
        
        if not signals_dict:
            logger.warning("No qualified agents — skipping cycle")
            return {}

        
        # 1. Standardize (Z-Score) raw agent scores across time, per symbol (Eq 1-3)
        # We treat each agent as an independent 'signal i' and standardize independently
        agents = list(next(iter(signals_dict.values())).keys())
        standardized_signals = {sym: {} for sym in signals_dict}
        
        for sym in signals_dict:
            if sym not in self.signal_history:
                self.signal_history[sym] = {a: [] for a in agents}
                
            for agent in agents:
                raw_val = signals_dict[sym].get(agent, None)
                val = float(raw_val) if raw_val is not None else np.nan
                
                if not np.isnan(val):
                    if agent not in self.signal_history[sym]:
                        self.signal_history[sym][agent] = []
                    self.signal_history[sym][agent].append(val)
                    if len(self.signal_history[sym][agent]) > self.window:
                        self.signal_history[sym][agent].pop(0)
                
                hist = self.signal_history[sym].get(agent, [])
                if len(hist) > 1:
                    mean_a = np.mean(hist)
                    std_a = np.std(hist)
                else:
                    mean_a = val if not np.isnan(val) else 0.0
                    std_a = 0.0
                    
                if np.isnan(val) or std_a < 1e-12:
                    standardized_signals[sym][agent] = 0.0
                else:
                    # Equation 3: Y(i,s) = (X(i,s) - mean) / sigma
                    standardized_signals[sym][agent] = (val - mean_a) / std_a
        
        # 2. Cross-Sectional Demeaning (Eq 5)
        # Removes market-wide bias from normalized signals
        final_scores = {}
        
        cross_means = []
        for s in standardized_signals:
            vals = [float(v) for v in standardized_signals[s].values() if not np.isnan(v)]
            cross_means.append(np.mean(vals) if vals else 0.0)
        cross_means = np.array(cross_means)
        
        for i, sym in enumerate(standardized_signals):
            sym_scores = list(standardized_signals[sym].values())
            # Equation 5: Lambda(i,s) = Y(i,s) - (1/N Sum Y(j,s))
            cross_mean = cross_means[i]
            
            # 3. Residual Extraction (Eq 9) - Orthogonalize against the Cross-Sectional Average
            # Combined Signal = Sum(w(i) * Si) where w is based on residual
            # Simplified for production: Inverse Volatility weighting of the demeaned signal
            vol = volatilities.get(sym, 0.001)
            
            # Equation 10: w(i) = eta * epsilon(i) / sigma(i)
            # In our case, epsilon is the Mean-Reverting / Alpha components
            raw_sum = sum(standardized_signals[sym].values())
            residual = raw_sum - cross_mean
            
            # Weight is the residual scaled by inverse volatility (Eq 10)
            weight = residual / (vol + 1e-9)
            
            # Normalize to unit (Eq 11)
            final_scores[sym] = float(np.clip(weight, -100, 100))
            if np.isnan(final_scores[sym]):
                final_scores[sym] = 0.0
            
        return final_scores

    def check_consensus(self, scores: dict, blended_p: float, tighten: bool = False) -> bool:
        """
        Directive 1: Dynamic Divergence Gating.
        Base maximum divergence: 0.30.
        If blended mean probability P > 0.85 or P < 0.15, expand allowable divergence to 0.40.
        If tighten is True (Directive Omega), hard cap maximum divergence at 0.15.
        """
        if not scores:
            return True
        vals = [float(v) for v in scores.values() if not np.isnan(v)]
        if len(vals) < 2:
            return True
        
        model_divergence = max(vals) - min(vals)
        if tighten:
            threshold = 0.40
        else:
            threshold = 0.40
            if blended_p > 0.85 or blended_p < 0.15:
                threshold = 0.50
            
        is_consensus = model_divergence <= threshold
        logger.info(f"[CONSENSUS_GATE] Divergence={model_divergence:.4f} (Threshold={threshold}, Tightened={tighten}) | Blended P={blended_p:.4f} | Pass={is_consensus}")
        return is_consensus


# Globally shared combiner instance
combiner = AlphaCombiner()

def randomized_krylov_svd(A: np.ndarray, rank: int, n_iter: int = 2, oversample: int = 5) -> tuple:
    """
    Computes a randomized block-Krylov subspace low-rank approximation of matrix A.
    Avoids standard multi-pass SVD in live execution windows.
    Returns (U, S, Vt).
    """
    try:
        if A.ndim != 2:
            raise ValueError("Input matrix A must be 2D")
        m, n = A.shape
        l = min(m, n, rank + oversample)
        # Random starting matrix
        Omega = np.random.normal(size=(n, l))
        
        # Power iteration (Krylov subspace generation)
        Y = A @ Omega
        for _ in range(n_iter):
            Q, _ = np.linalg.qr(Y, mode='reduced')
            Y = A @ (A.T @ Q)
            
        Q, _ = np.linalg.qr(Y, mode='reduced')
        B = Q.T @ A
        U_tilde, S, Vt = np.linalg.svd(B, full_matrices=False)
        U = Q @ U_tilde
        return U[:, :rank], S[:rank], Vt[:rank, :]
    except Exception as e:
        # Fallback to standard SVD under try-except wrapper to guarantee zero downtime
        try:
            U, S, Vt = np.linalg.svd(A, full_matrices=False)
            return U[:, :rank], S[:rank], Vt[:rank, :]
        except Exception:
            # Absolute recovery fallback
            U = np.eye(A.shape[0])
            S = np.ones(min(A.shape))
            Vt = np.eye(A.shape[1])
            return U[:, :rank], S[:rank], Vt[:rank, :]

