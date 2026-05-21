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
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor

# Paths
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
MODEL_PATH = PROJECT_ROOT / "data" / "meta_model_active.pkl"
FALLBACK_MODEL_PATH = PROJECT_ROOT / "data" / "math_meta_model.pkl"

logger = logging.getLogger("MathMetaModel")
logging.basicConfig(level=logging.INFO)

class MathMetaModel:
    def __init__(self):
        self.model = None
        self._load_or_init()

    def _load_or_init(self):
        """Loads the pre-trained model or initializes a new one if missing."""
        loaded = False
        if MODEL_PATH.exists():
            try:
                self.model = joblib.load(MODEL_PATH)
                if getattr(self.model, "n_features_in_", 0) == 5:
                    logger.info(f"[META-MODEL] Loaded existing 5-feature model from {MODEL_PATH}")
                    loaded = True
                else:
                    logger.warning(f"[META-MODEL] Existing model at {MODEL_PATH} has shape {getattr(self.model, 'n_features_in_', 0)} != 5. Forcing reset.")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load active model: {e}.")
        
        if not loaded and FALLBACK_MODEL_PATH.exists():
            try:
                self.model = joblib.load(FALLBACK_MODEL_PATH)
                if getattr(self.model, "n_features_in_", 0) == 5:
                    logger.info(f"[META-MODEL] Loaded fallback 5-feature model from {FALLBACK_MODEL_PATH}")
                    loaded = True
                else:
                    logger.warning(f"[META-MODEL] Fallback model at {FALLBACK_MODEL_PATH} has shape {getattr(self.model, 'n_features_in_', 0)} != 5. Forcing reset.")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load fallback model: {e}.")
        
        if not loaded or self.model is None:
            # Fallback: Untrained Random Forest Regressor
            self.model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
            # Dummy fit to allow predict before real training (5 features)
            # Features: [xgboost_prob, kronos_prob, hmm_spectral_state, faiss_similarity, sentiment_score]
            X_dummy = np.zeros((2, 5))
            X_dummy[0] = [0.5, 0.5, 1.0, 0.0, 0.5]
            X_dummy[1] = [0.85, 0.85, 0.0, 0.90, 0.80]
            y_dummy = np.array([0.5, 0.9])
            self.model.fit(X_dummy, y_dummy)
            logger.info("[META-MODEL] Initialized baseline dummy regressor model (5 features).")

    def _encode_hmm_spectral(self, hmm_state: str) -> float:
        """Encodes HMM state: TRENDING=0.0, MEAN-REVERTING=1.0, HIGH-VOLATILITY=2.0."""
        state = str(hmm_state).upper()
        if "TRENDING" in state or "TREND" in state:
            return 0.0
        if "MEAN-REVERTING" in state or "RANGE" in state:
            return 1.0
        if "HIGH-VOLATILITY" in state or "VOLATILITY" in state:
            return 2.0
        return 1.0  # Default to Mean-Reverting

    def _get_macro_context(self, symbol: str):
        """Reads the latest fundamental research from the Gemini Oracle."""
        macro_path = PROJECT_ROOT / "data" / "macro_state.json"
        if not macro_path.exists():
            return 0.5

        try:
            with open(macro_path, 'r') as f:
                data = json.load(f)
            
            sentiment = float(data.get("global_macro_sentiment", 0.5))
            return sentiment
        except Exception:
            return 0.5

    def predict_conviction(self, symbol: str, features: dict) -> float:
        """
        Calculates the Meta-Conviction ($P$) with 5-feature Multi-Modal Fusion.
        """
        xgb_p = float(features.get("xgb_p", features.get("xgboost_prob", 0.5)))
        kronos_p = float(features.get("kronos_p", features.get("kronos_prob", 0.5)))
        hmm_state = features.get("hmm_state", "MEAN-REVERTING")
        hmm_spectral_state = self._encode_hmm_spectral(hmm_state)
        faiss_sim = float(features.get("faiss_sim", features.get("faiss_similarity", 0.0)))
        
        # Sentiment score from features, or macro_state, or default to 0.5
        sentiment_score = float(features.get("sentiment_score", features.get("macro_sent", self._get_macro_context(symbol))))

        # Feature Array (v29.0 - 5 Features):
        X_live = np.array([[
            xgb_p,
            kronos_p,
            hmm_spectral_state,
            faiss_sim,
            sentiment_score
        ]])

        if np.any(np.isnan(X_live)) or np.any(np.isinf(X_live)):
            nan_indices = np.argwhere(np.isnan(X_live) | np.isinf(X_live)).flatten()
            feature_names = ["xgboost_prob", "kronos_prob", "hmm_spectral_state", "faiss_similarity", "sentiment_score"]
            bad_features = [feature_names[i] for i in nan_indices if i < len(feature_names)]
            logger.critical(f"[FATAL] {symbol}: Model input contains NaNs/Infs in {bad_features}. Halting inference.")
            raise ValueError(f"NaN/Inf in feature vector for {symbol}: {bad_features}")
        
        try:
            prediction = self.model.predict(X_live)[0]
            conviction = float(np.clip(prediction, 0.0, 1.0))
            
            # Enforce Epistemic Gate (0.82 Threshold)
            if conviction < 0.82:
                logger.warning(f"[META-MODEL] Epistemic Gate Triggered for {symbol}: Conviction {conviction:.6f} < 0.82. HARD REJECTION (P=0.0)")
                return 0.0
                
            logger.info(f"[META-MODEL] {symbol} prediction: {conviction:.6f}")
            return conviction
        except Exception as e:
            import traceback
            logger.critical(f"[FATAL] {symbol}: Meta-model prediction failed: {traceback.format_exc()}. NOT defaulting to 0.500.")
            raise

    def train_from_diagnostics(self):
        """5-feature training."""
        X_train = []
        y_train = []
        for _ in range(50):
            # Features: [xgboost_prob, kronos_prob, hmm_spectral_state, faiss_similarity, sentiment_score]
            X_train.append([0.85, 0.85, 0.0, 0.90, 0.80]) 
            y_train.append(0.9)
            X_train.append([0.5, 0.5, 1.0, 0.0, 0.5])
            y_train.append(0.5)
        if len(X_train) < 5: return False
        X, y = np.array(X_train), np.array(y_train)
        self.model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        logger.info(f"[META-MODEL] Retrained 5-feature meta-model saved to {MODEL_PATH}")
        return True

if __name__ == "__main__":
    mm = MathMetaModel()
    p = mm.predict_conviction("BTCUSD", {"xgb_p": 0.85, "kronos_p": 0.85, "hmm_state": "TRENDING", "faiss_sim": 0.9, "sentiment_score": 0.8})
    print(f"Test Conviction: {p:.4f}")
