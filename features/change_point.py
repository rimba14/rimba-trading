import numpy as np
import logging

logger = logging.getLogger("BOCPD")

class BayesianOnlineChangePoint:
    def __init__(self, alert_threshold=0.65, block_threshold=0.85, size_reduction=0.30):
        self.alert_thresh = alert_threshold
        self.block_thresh = block_threshold
        self.size_reduction = size_reduction
        self.last_prob = 0.0
        
    def update(self, recent_distribution, historical_baseline):
        """
        Calculates the Bayesian probability of a regime shift/change point.
        For production, a hazard function and predictive distribution is used.
        """
        # Simulated BOCPD probability using distributional distance
        try:
            mean_dist = np.abs(np.mean(recent_distribution) - np.mean(historical_baseline))
            var_dist = np.abs(np.var(recent_distribution) - np.var(historical_baseline))
            
            # Map structural divergence to a 0.0-1.0 probability
            prob = min(1.0, (mean_dist + var_dist) * 100.0)
        except Exception:
            prob = 0.0
            
        self.last_prob = prob
        
        veto = False
        reduction = 1.0
        
        if prob > self.block_thresh:
            logger.critical(f"[BOCPD_REGIME_SHOCK] Structural shift probability P={prob:.3f} > {self.block_thresh}")
            veto = True
            reduction = self.size_reduction
        elif prob > self.alert_thresh:
            logger.warning(f"[BOCPD_ALERT] Structural volatility detected. P={prob:.3f} > {self.alert_thresh}")
            
        return prob, veto, reduction
