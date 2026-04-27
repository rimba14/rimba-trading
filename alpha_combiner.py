import numpy as np
import pandas as pd

class AlphaCombiner:
    """
    Implementation of 'A Unified Framework for Alpha Extraction and Signal Combination'
    Eq (1-12) for Residual Orthogonalization and Multi-Factor Blending.
    """
    def __init__(self, window=20):
        self.window = window
        self.signal_history = {} # sym -> list of raw scores
        
    def process_signals(self, signals_dict, volatilities):
        """
        signals_dict: { 'sym': { 'agent_1': score, 'agent_2': score ... } }
        volatilities: { 'sym': current_atr }
        """
        if not signals_dict: return {}
        
        # 1. Standardize (Z-Score) raw agent scores across symbols (Eq 1-3)
        # We treat each agent as an independent 'signal i'
        agents = list(next(iter(signals_dict.values())).keys())
        standardized_signals = {sym: {} for sym in signals_dict}
        
        for agent in agents:
            raw_scores = [signals_dict[s][agent] for s in signals_dict]
            mean_a = np.mean(raw_scores)
            std_a = np.std(raw_scores) + 1e-9
            
            for sym in signals_dict:
                # Equation 3: Y(i,s) = X(i,s) / sigma
                standardized_signals[sym][agent] = (signals_dict[sym][agent] - mean_a) / std_a
        
        # 2. Cross-Sectional Demeaning (Eq 5)
        # Removes market-wide bias from normalized signals
        final_scores = {}
        for sym in standardized_signals:
            sym_scores = list(standardized_signals[sym].values())
            # Equation 5: Lambda(i,s) = Y(i,s) - (1/N Sum Y(j,s))
            cross_mean = np.mean([list(standardized_signals[s].values()) for s in standardized_signals])
            
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

# Globally shared combiner instance
combiner = AlphaCombiner()
