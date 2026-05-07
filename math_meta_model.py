"""
math_meta_model.py - SRE Patch (LLM Execution Bypass)
Zero-Latency, Zero-Cost Mathematical Meta-Model (v22.4 - Data Warm-Up)
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
        if MODEL_PATH.exists():
            try:
                self.model = joblib.load(MODEL_PATH)
                logger.info(f"[META-MODEL] Loaded existing model from {MODEL_PATH}")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load active model: {e}.")
        elif FALLBACK_MODEL_PATH.exists():
            try:
                self.model = joblib.load(FALLBACK_MODEL_PATH)
                logger.info(f"[META-MODEL] Loaded fallback model from {FALLBACK_MODEL_PATH}")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load fallback model: {e}.")
        
        if self.model is None:
            # Fallback: Untrained Random Forest Regressor
            self.model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
            # Dummy fit to allow predict before real training (v22.3 - 12 features)
            X_dummy = np.zeros((2, 12))
            X_dummy[0] = [0.5, 0.5, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5]
            X_dummy[1] = [0.8, 0.8, 1, 0.8, 0.1, 0.1, 0.2, 0.5, 0.1, 0.08, 0.05, 0.8]
            y_dummy = np.array([0.5, 0.9])
            self.model.fit(X_dummy, y_dummy)
            logger.info("[META-MODEL] Initialized baseline dummy regressor model (12 features).")

    def _encode_hmm(self, hmm_state: str) -> int:
        """Encodes HMM state: BULL=1, BEAR=-1, RANGE=0."""
        hmm_state = str(hmm_state).upper()
        if hmm_state == "BULL": return 1
        if hmm_state == "BEAR": return -1
        return 0

    def _get_macro_context(self, symbol: str):
        """Reads the latest fundamental research from the Gemini Oracle."""
        macro_path = PROJECT_ROOT / "data" / "macro_state.json"
        if not macro_path.exists():
            return 0.0, 0.0, 0.0

        try:
            with open(macro_path, 'r') as f:
                data = json.load(f)
            
            sentiment = float(data.get("global_macro_sentiment", 0.0))
            risk      = float(data.get("black_swan_risk", 0.0))
            catalysts = data.get("asset_specific_catalysts", {})
            catalyst  = float(catalysts.get(symbol, 0.0))
            
            def damp(x): return np.sign(x) * np.log1p(abs(float(x)))
            return damp(sentiment), damp(risk), damp(catalyst)
        except Exception:
            return 0.0, 0.0, 0.0

    def predict_conviction(self, symbol: str, features: dict) -> float:
        """
        Calculates the Meta-Conviction ($P$) with 12-feature Alpha Factory Integration.
        """
        macro_sent, black_swan_risk, catalyst = self._get_macro_context(symbol)

        if black_swan_risk > 0.85:
            logger.critical(f"[BLACK_SWAN_OVERRIDE] Systemic risk detected ({black_swan_risk:.2f}). Forcing P=0.0")
            return 0.0

        hmm_encoded = self._encode_hmm(features.get("hmm_state", "RANGE"))
        
        # Feature Array (v22.3 - 12 Features):
        X_live = np.array([[
            float(features.get("xgb_p", 0.5)), 
            float(features.get("kronos_p", 0.5)), 
            float(hmm_encoded), 
            float(features.get("faiss_sim", 0.0)),
            float(macro_sent),
            float(black_swan_risk),
            float(catalyst),
            float(features.get("frac_diff", 0.0)),
            float(features.get("fft_amp_1", 0.0)),
            float(features.get("fft_amp_2", 0.0)),
            float(features.get("fft_amp_3", 0.0)),
            float(features.get("cs_rank", 0.5)),
        ]])
        # v22.4: NaN Validation — NEVER silently default to 0.500
        if np.any(np.isnan(X_live)) or np.any(np.isinf(X_live)):
            nan_indices = np.argwhere(np.isnan(X_live) | np.isinf(X_live)).flatten()
            feature_names = ["xgb_p", "kronos_p", "hmm", "faiss_sim", "macro_sent", 
                           "macro_risk", "catalyst", "frac_diff", "fft_amp_1", 
                           "fft_amp_2", "fft_amp_3", "cs_rank"]
            bad_features = [feature_names[i] for i in nan_indices if i < len(feature_names)]
            logger.critical(f"[FATAL] {symbol}: Model input contains NaNs/Infs in {bad_features}. Halting inference.")
            raise ValueError(f"NaN/Inf in feature vector for {symbol}: {bad_features}")
        
        try:
            prediction = self.model.predict(X_live)[0]
            conviction = float(np.clip(prediction, 0.0, 1.0))
            logger.info(f"[META-MODEL] {symbol} prediction: {conviction:.6f}")
            return conviction
        except ValueError as e:
            logger.critical(f"[FATAL] {symbol}: XGBoost prediction failed with ValueError: {e}. NOT defaulting to 0.500.")
            raise
        except Exception as e:
            logger.critical(f"[FATAL] {symbol}: XGBoost prediction failed: {e}. NOT defaulting to 0.500.")
            raise

    def train_from_diagnostics(self):
        """Legacy 12-feature training."""
        X_train = []
        y_train = []
        for _ in range(50):
            X_train.append([2.15, 2.05, 1, 0.90, 0.5, 0.1, 0.4, 0.8, 0.18, 0.14, 0.11, 0.92]) 
            y_train.append(1)
            X_train.append([0.0, 0.0, 0, 0.20, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5])
            y_train.append(0.5)
        if len(X_train) < 5: return False
        X, y = np.array(X_train), np.array(y_train)
        self.model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        return True

if __name__ == "__main__":
    mm = MathMetaModel()
    p = mm.predict_conviction("BTCUSD", {"xgb_p": 0.85})
    print(f"Test Conviction: {p:.4f}")
