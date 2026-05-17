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

        
        # 1. Standardize (Z-Score) raw agent scores across symbols (Eq 1-3)
        # We treat each agent as an independent 'signal i'
        agents = list(next(iter(signals_dict.values())).keys())
        standardized_signals = {sym: {} for sym in signals_dict}
        
        for agent in agents:
            raw_scores = np.array(
                [float(signals_dict[s].get(agent, np.nan) or np.nan) for s in signals_dict],
                dtype=np.float64,
            )
            mean_a = np.nanmean(raw_scores)
            std_a = np.nanstd(raw_scores)
            # Guard: if all values are NaN or std is zero, skip normalization
            if np.isnan(mean_a) or std_a < 1e-12:
                for sym in signals_dict:
                    standardized_signals[sym][agent] = 0.0
                continue
            
            for sym in signals_dict:
                raw_val = signals_dict[sym].get(agent, None)
                val = float(raw_val) if raw_val is not None else np.nan
                if np.isnan(val):
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

# Globally shared combiner instance
combiner = AlphaCombiner()
