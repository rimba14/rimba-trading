import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
import collections

class ConvictionMoEEngine:
    def __init__(self):
        # Local subquadratic estimators calibrated for localized distributions
        self.expert_trending = LogisticRegression(C=1.0)
        self.expert_mean_reverting = LogisticRegression(C=1.0)
        self.expert_high_vol = LogisticRegression(C=1.0)
        
        # Rolling calibration loop memory tracking (500 bars window)
        self.calibration_window = 500
        self.historical_predictions = collections.deque(maxlen=self.calibration_window)
        self.historical_outcomes = collections.deque(maxlen=self.calibration_window)
        self.calibrator = IsotonicRegression(out_of_bounds='clip')
        
        # Inductive Conformal Prediction calibration scores
        self.conformal_calibration_scores = np.array([0.05, 0.10, 0.15, 0.20]) # Seed array

    def compute_moe_routing_weights(self, w_state, feature_vector):
        """
        Softmax gating router mapping the asset distribution state to specific experts.
        """
        # Conceptual localized thresholding logic based on structural state parameters
        if w_state < 0.25:
            scores = [5.0, 1.0, 0.5] # Favor Mean Reverting
        elif w_state >= 0.25 and w_state < 0.45:
            scores = [1.0, 5.0, 0.5] # Favor Trending
        else:
            scores = [0.5, 1.0, 5.0] # Favor High Volatility
            
        exps = np.exp(scores - np.max(scores))
        return exps / np.sum(exps)

    def calculate_raw_moe_probability(self, feature_vector, weights):
        x = feature_vector.reshape(1, -1)
        
        # Safely compute continuous prediction scores across sub-experts
        p_trend = self.expert_trending.predict_proba(x)[0][1]
        p_range = self.expert_mean_reverting.predict_proba(x)[0][1]
        p_vol = self.expert_high_vol.predict_proba(x)[0][1]
        
        raw_probability = (p_trend * weights[0]) + (p_range * weights[1]) + (p_vol * weights[2])
        return raw_probability

    def update_temporal_calibration(self, raw_pred, realized_outcome):
        self.historical_predictions.append(raw_pred)
        self.historical_outcomes.append(realized_outcome)
        
        if len(self.historical_predictions) >= 100:
            self.calibrator.fit(list(self.historical_predictions), list(self.historical_outcomes))

    def predict_conformal_conviction_interval(self, feature_vector, w_state, alpha=0.10):
        """
        Processes multi-modal arrays and returns temporal, non-parametric bounded prediction intervals.
        """
        routing_weights = self.compute_moe_routing_weights(w_state, feature_vector)
        raw_prob = self.calculate_raw_moe_probability(feature_vector, routing_weights)
        
        # 1. Apply Temporal Isotonic Recalibration Layer
        if len(self.historical_predictions) >= 100:
            calibrated_prob = float(self.calibrator.transform([raw_prob])[0])
        else:
            calibrated_prob = raw_prob # Fallback if calibration data has not compiled yet
            
        # 2. Apply Inductive Conformal Prediction Coverage Bands
        q_index = int(np.ceil((1.0 - alpha) * (len(self.conformal_calibration_scores) + 1))) - 1
        q_index = np.clip(q_index, 0, len(self.conformal_calibration_scores) - 1)
        margin = self.conformal_calibration_scores[q_index]
        
        p_lower = np.clip(calibrated_prob - margin, 0.0, 1.0)
        p_upper = np.clip(calibrated_prob + margin, 0.0, 1.0)
        uncertainty_width = p_upper - p_lower
        
        return {
            "p_lower": p_lower,
            "p_upper": p_upper,
            "calibrated_midpoint": calibrated_prob,
            "uncertainty_width": uncertainty_width,
            "neutral_ground_override": False
        }

    def generate_neutral_fallback_vector(self):
        """
        Forces a safe 50/50 fallback profile when anomalous conditions are encountered.
        """
        return {
            "p_lower": 0.5000,
            "p_upper": 0.5000,
            "calibrated_midpoint": 0.5000,
            "uncertainty_width": 0.0000,
            "neutral_ground_override": True
        }
