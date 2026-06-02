import numpy as np
import logging
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger("ADV_VALIDATOR")

class AdversarialValidator:
    def __init__(self, window_bars=500, auc_threshold=0.70):
        self.window = window_bars
        self.auc_threshold = auc_threshold
        self.model = LogisticRegression(max_iter=100)
        
    def score_domain_shift(self, historical_features, live_features):
        """
        Trains an adversarial classifier to distinguish between historical training distribution
        and the live incoming bar flow distribution.
        """
        try:
            # Shape check
            if len(historical_features) == 0 or len(live_features) == 0:
                return 0.50, False
                
            # Flatten or reshape if necessary, assuming 2D feature matrices
            if len(historical_features.shape) > 2:
                historical_features = historical_features.reshape(historical_features.shape[0], -1)
            if len(live_features.shape) > 2:
                live_features = live_features.reshape(live_features.shape[0], -1)
                
            # Label historical as 0, live as 1
            X = np.vstack((historical_features, live_features))
            y = np.hstack((np.zeros(len(historical_features)), np.ones(len(live_features))))
            
            self.model.fit(X, y)
            preds = self.model.predict_proba(X)[:, 1]
            auc = roc_auc_score(y, preds)
            
            if auc < self.auc_threshold:
                logger.critical(f"[DOMAIN_SHIFT_REJECT] Adversarial AUC {auc:.3f} < {self.auc_threshold}. Flow distribution degraded.")
                return auc, True
                
            return auc, False
        except Exception as e:
            logger.warning(f"Adversarial validation failed: {e}")
            # Fail-open if the matrix causes fitting issues
            return 1.0, False
