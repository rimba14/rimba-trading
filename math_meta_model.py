"""
math_meta_model.py - SRE Patch (LLM Execution Bypass)
Zero-Latency, Zero-Cost Mathematical Meta-Model (v29.0 - Multi-Modal Swing Trading)
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib
import time
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor

# Paths
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
MODEL_PATH = PROJECT_ROOT / "data" / "meta_model_active.pkl"
FALLBACK_MODEL_PATH = PROJECT_ROOT / "data" / "math_meta_model.pkl"

logger = logging.getLogger("MathMetaModel")
logging.basicConfig(level=logging.INFO)

class MathMetaModel:
    WASSERSTEIN_MAX_THRESHOLD = 3.0 # Strict statistical threshold for Epistemic Gate

    def __init__(self):
        self.logger = logger
        self.expert_trending = None
        self.expert_mean_reverting = None
        self.expert_high_vol = None
        self._load_experts_or_init()
        self.calibration_queue = []
        self._load_calibration_queue()

    def _load_experts_or_init(self):
        """Loads the pre-trained expert models or initializes new ones if missing."""
        # Paths
        global EXPERT_TRENDING_PATH, EXPERT_MEAN_REVERTING_PATH, EXPERT_HIGH_VOL_PATH
        EXPERT_TRENDING_PATH = PROJECT_ROOT / "data" / "expert_trending.pkl"
        EXPERT_MEAN_REVERTING_PATH = PROJECT_ROOT / "data" / "expert_mean_reverting.pkl"
        EXPERT_HIGH_VOL_PATH = PROJECT_ROOT / "data" / "expert_high_vol.pkl"

        def load_expert(path, name):
            if path.exists():
                try:
                    model = joblib.load(path)
                    n_features = getattr(model, "n_features_in_", 0)
                    if n_features == 7:
                        logger.info(f"[META-MODEL] Loaded {name} from {path}")
                        return model
                    else:
                        logger.warning(f"[META-MODEL] Model {name} at {path} has shape {n_features} != 7. Resetting.")
                except Exception as e:
                    logger.warning(f"[META-MODEL] Failed to load {name}: {e}")
            
            # Fallback dummy regressor fit with 7 features:
            # [xgboost_prob, kronos_prob, wasserstein_state, faiss_sim, sentiment_divergence_delta, volatility_ratio, ofi_velocity]
            model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
            X_dummy = np.zeros((2, 7))
            X_dummy[0] = [0.5, 0.5, 0.0, 0.0, 0.0, 1.0, 0.0]
            X_dummy[1] = [0.85, 0.85, 1.0, 0.90, 0.5, 1.5, 0.8]
            y_dummy = np.array([0.5, 0.9])
            model.fit(X_dummy, y_dummy)
            logger.info(f"[META-MODEL] Initialized baseline dummy regressor for {name}.")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(model, path)
            except Exception as e:
                logger.error(f"[META-MODEL] Failed to write fallback model to {path}: {e}")
            return model

        self.expert_trending = load_expert(EXPERT_TRENDING_PATH, "Expert_Trending")
        self.expert_mean_reverting = load_expert(EXPERT_MEAN_REVERTING_PATH, "Expert_MeanReverting")
        self.expert_high_vol = load_expert(EXPERT_HIGH_VOL_PATH, "Expert_HighVol")

    def _load_calibration_queue(self):
        global CALIBRATION_CACHE_PATH
        CALIBRATION_CACHE_PATH = PROJECT_ROOT / "data" / "calibration_queue.json"
        if CALIBRATION_CACHE_PATH.exists():
            try:
                with open(CALIBRATION_CACHE_PATH, "r") as f:
                    self.calibration_queue = json.load(f)
                logger.info(f"[META-MODEL] Loaded calibration queue with {len(self.calibration_queue)} samples.")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load calibration queue: {e}")
        
        # Seed the queue if empty/too small to avoid cold start issues
        if len(self.calibration_queue) < 50:
            logger.info("[META-MODEL] Seeding calibration queue with synthetic outcomes.")
            # Seed with 500 samples representing a reasonable regressor accuracy
            np.random.seed(42)
            for _ in range(500):
                p = np.random.uniform(0.1, 0.9)
                y = 1.0 if np.random.random() < p else 0.0
                self.calibration_queue.append([p, y])
            self._save_calibration_queue()

    def _save_calibration_queue(self):
        try:
            CALIBRATION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CALIBRATION_CACHE_PATH, "w") as f:
                json.dump(self.calibration_queue[-500:], f)
        except Exception as e:
            logger.warning(f"[META-MODEL] Failed to save calibration queue: {e}")

    def add_outcome(self, p_raw, outcome):
        """Adds a completed outcome to the calibration queue."""
        self.calibration_queue.append([float(p_raw), float(outcome)])
        if len(self.calibration_queue) > 500:
            self.calibration_queue.pop(0)
        self._save_calibration_queue()

    def get_conviction(self, feature_array, symbol):
        """Standard fallback mapping feature_array to dictionary for predict_conviction."""
        # Expecting at least 6 features. Fill if needed.
        feature_array = list(feature_array)
        while len(feature_array) < 6:
            feature_array.append(0.0)
            
        features = {
            "xgb_p": feature_array[0],
            "kronos_p": feature_array[1],
            "wasserstein_state": feature_array[2],
            "faiss_sim": feature_array[3],
            "volatility_ratio": feature_array[4],
            "ofi_velocity": feature_array[5],
        }
        res = self.predict_conviction(symbol, features)
        if isinstance(res, dict):
            if res.get("trust_gate_failed", False):
                return 0.0
            return res.get("p_calibrated", 0.5)
        return float(res)

    def predict_conviction(self, symbol: str, features: dict) -> dict:
        """
        Calculates Meta-Conviction with Mixture-of-Experts, Conformal Predictions,
        and Wasserstein Epistemic Gate logic.
        Returns a dict of conformal interval, width, calibration, and gate status.
        """
        # 1. Wasserstein State Gate Check
        failed, wasserstein_val = self._check_epistemic_gate(features)
        if failed:
            return self._gate_failure_result()

        # 2. Extract and Validate Features
        model_input = self._extract_and_validate_features(symbol, features, wasserstein_val)
        if model_input is None:
            return self._gate_failure_result()

        # 3. MoE Routing weights
        weights = self._calculate_moe_routing_weights(features)

        # Individual Expert Inference and Dot product
        p_raw = self._perform_moe_inference(weights, model_input)

        # 4. Temporal Isotonic Calibration
        p_calibrated = self._apply_isotonic_calibration(p_raw)

        # 5. Conformal Prediction Interval calculation
        prediction_interval, uncertainty_width = self._calculate_conformal_interval(p_calibrated)

        return {
            "prediction_interval": prediction_interval,
            "uncertainty_width": uncertainty_width,
            "trust_gate_failed": False,
            "p_calibrated": p_calibrated
        }

    def _gate_failure_result(self) -> dict:
        """Standard return dict for when a gate or validation fails."""
        return {
            "prediction_interval": [0.5, 0.5],
            "uncertainty_width": 0.0,
            "trust_gate_failed": True,
            "p_calibrated": 0.5
        }

    def _check_epistemic_gate(self, features: dict) -> tuple[bool, float]:
        """Checks if the Wasserstein value is within the acceptable threshold."""
        try:
            wasserstein_val = float(features.get("wasserstein_state", 0.0))
        except (ValueError, TypeError):
            wasserstein_val = 0.0

        if wasserstein_val > self.WASSERSTEIN_MAX_THRESHOLD:
            self.logger.warning(
                f"[EPISTEMIC_GATE_TRIGGERED]: Live distribution has drifted into "
                f"an unverifiable regime ({wasserstein_val:.4f} > {self.WASSERSTEIN_MAX_THRESHOLD})"
            )
            return True, wasserstein_val
        return False, wasserstein_val

    def _extract_and_validate_features(self, symbol: str, features: dict, wasserstein_val: float) -> list:
        """Extracts and validates features, returning a feature list or None if invalid."""
        xgb_p = float(features.get("xgb_p", features.get("xgboost_prob", 0.5)))
        kronos_p = float(features.get("kronos_p", features.get("kronos_prob", 0.5)))
        faiss_sim = float(features.get("faiss_sim", features.get("faiss_similarity", 0.0)))
        volatility_ratio = float(features.get("volatility_ratio", 1.0))
        ofi_velocity = float(features.get("ofi_velocity", 0.0))
        sentiment_divergence_delta = float(features.get("sentiment_divergence_delta", 0.0))

        # Check for NaN/Infs in critical inputs
        for val, name in [(xgb_p, "xgb_p"), (kronos_p, "kronos_p"), (faiss_sim, "faiss_sim")]:
            if np.isnan(val) or np.isinf(val):
                self.logger.critical(f"[MATRIX_CORRUPTION] NaN/Inf in {name} for {symbol}. Vetoing inference.")
                return None

        return [
            xgb_p,
            kronos_p,
            wasserstein_val,
            faiss_sim,
            sentiment_divergence_delta,
            volatility_ratio,
            ofi_velocity
        ]

    def _calculate_moe_routing_weights(self, features: dict) -> tuple[float, float, float]:
        """Calculates normalized weights for MoE experts based on the current regime."""
        routing_probs = features.get("wasserstein_routing_probs", None)
        if not routing_probs:
            # Fallback based on regime string
            w_state_str = str(features.get("hmm_state", "RANGE")).upper()
            if "TREND" in w_state_str:
                routing_probs = {"LOW-VOL TREND": 0.8, "HIGH-VOL MEAN REVERSION": 0.1, "CRISIS TAIL": 0.1}
            elif "CRISIS" in w_state_str:
                routing_probs = {"LOW-VOL TREND": 0.1, "HIGH-VOL MEAN REVERSION": 0.1, "CRISIS TAIL": 0.8}
            else:
                routing_probs = {"LOW-VOL TREND": 0.1, "HIGH-VOL MEAN REVERSION": 0.8, "CRISIS TAIL": 0.1}

        w_trending = float(routing_probs.get("LOW-VOL TREND", 0.33))
        w_mean_rev = float(routing_probs.get("HIGH-VOL MEAN REVERSION", 0.33))
        w_high_vol = float(routing_probs.get("CRISIS TAIL", 0.33))
        
        total_w = w_trending + w_mean_rev + w_high_vol + 1e-9
        return w_trending / total_w, w_mean_rev / total_w, w_high_vol / total_w

    def _perform_moe_inference(self, weights: tuple[float, float, float], model_input: list) -> float:
        """Calculates the weighted average prediction from all experts."""
        w_trending, w_mean_rev, w_high_vol = weights
        p_trending = float(self.expert_trending.predict([model_input])[0])
        p_mean_rev = float(self.expert_mean_reverting.predict([model_input])[0])
        p_high_vol = float(self.expert_high_vol.predict([model_input])[0])

        return w_trending * p_trending + w_mean_rev * p_mean_rev + w_high_vol * p_high_vol

    def _apply_isotonic_calibration(self, p_raw: float) -> float:
        """Applies isotonic regression calibration if enough samples are available."""
        if len(self.calibration_queue) < 10:
            return p_raw

        try:
            from sklearn.isotonic import IsotonicRegression
            X_cal = [item[0] for item in self.calibration_queue]
            y_cal = [item[1] for item in self.calibration_queue]

            iso = IsotonicRegression(out_of_bounds='clip')
            iso.fit(X_cal, y_cal)
            return float(iso.predict([p_raw])[0])
        except Exception as e:
            self.logger.warning(f"[META-MODEL] Isotonic Regression failed: {e}. Using raw score.")
            return p_raw

    def _calculate_conformal_interval(self, p_calibrated: float) -> tuple[list[float], float]:
        """Calculates the conformal prediction interval and uncertainty width."""
        alpha = 0.10
        q = 0.15  # Fallback margin
        if len(self.calibration_queue) >= 10:
            try:
                non_conformity_scores = [abs(item[0] - item[1]) for item in self.calibration_queue]
                q = float(np.percentile(non_conformity_scores, (1.0 - alpha) * 100))
            except Exception as e:
                self.logger.warning(f"[META-MODEL] Conformal Prediction failed: {e}")

        p_lower = float(np.clip(p_calibrated - q, 0.0, 1.0))
        p_upper = float(np.clip(p_calibrated + q, 0.0, 1.0))
        return [p_lower, p_upper], p_upper - p_lower

    def optimize_hyperparameters(self, price_history: pd.Series, atr_series: pd.Series, n_bars: int = 500):
        """Unused hyperparameter optimizer placeholder for compatibility."""
        pass

    def train_from_diagnostics(self):
        """Retrains the 3 MoE experts with a mock dataset."""
        X_train = []
        y_train = []
        for _ in range(50):
            # 7 features
            X_train.append([0.85, 0.85, 1.0, 0.90, 0.05, 1.5, 0.8])
            y_train.append(0.9)
            X_train.append([0.5, 0.5, 2.0, 0.0, 0.5, 1.0, 0.0])
            y_train.append(0.5)
            
        if len(X_train) < 5: return False
        X, y = np.array(X_train), np.array(y_train)
        
        self.expert_trending = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        self.expert_trending.fit(X, y)
        joblib.dump(self.expert_trending, EXPERT_TRENDING_PATH)
        
        self.expert_mean_reverting = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        self.expert_mean_reverting.fit(X, y)
        joblib.dump(self.expert_mean_reverting, EXPERT_MEAN_REVERTING_PATH)
        
        self.expert_high_vol = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        self.expert_high_vol.fit(X, y)
        joblib.dump(self.expert_high_vol, EXPERT_HIGH_VOL_PATH)
        
        logger.info("[META-MODEL] Retrained 3 MoE experts.")
        return True

if __name__ == "__main__":
    mm = MathMetaModel()
    res = mm.predict_conviction("BTCUSD", {
        "xgb_p": 0.85,
        "kronos_p": 0.85,
        "wasserstein_state": 1.2,
        "faiss_sim": 0.9,
        "volatility_ratio": 1.2,
        "ofi_velocity": 0.5,
        "sentiment_divergence_delta": 0.1
    })
    print(f"Test Calibration Result: {res}")
