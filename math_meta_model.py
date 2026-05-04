"""
math_meta_model.py - SRE Patch (LLM Execution Bypass)
Zero-Latency, Zero-Cost Mathematical Meta-Model (v18.2)

Replaces the LLM "Judge" with a purely mathematical scikit-learn ensemble.
Combines XGBoost, Kronos, HMM Regime, and FAISS similarity into a final conviction score ($P$).
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib
from pathlib import Path

# Paths
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
SHAP_DIR = PROJECT_ROOT / "shap_diagnostics"
DIAG_DIR = PROJECT_ROOT / "pending_diagnostics"
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
            self.model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
            # Dummy fit to allow predict before real training
            # [XGB, Kronos, HMM, FAISS, Macro_Sent, Macro_Risk, Catalyst]
            X_dummy = np.array([[0.5, 0.5, 0, 0.0, 0.0, 0.0, 0.0], [0.8, 0.8, 1, 0.8, 0.1, 0.1, 0.2]])
            y_dummy = np.array([0.5, 0.9])
            self.model.fit(X_dummy, y_dummy)
            logger.info("[META-MODEL] Initialized baseline dummy regressor model.")

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
            return 0.0, 0.0, 0.0 # [sentiment, risk, catalyst]

        try:
            with open(macro_path, 'r') as f:
                data = json.load(f)
            
            sentiment = float(data.get("global_macro_sentiment", 0.0))
            risk      = float(data.get("black_swan_risk", 0.0))
            catalysts = data.get("asset_specific_catalysts", {})
            catalyst  = float(catalysts.get(symbol, 0.0))
            
            # Directive 2: Logarithmic Dampener (Prevent Macro Dominance)
            # Squeezes macro features to prevent them from commanding >65% importance.
            sentiment = np.sign(sentiment) * np.log1p(abs(sentiment))
            risk      = np.sign(risk) * np.log1p(abs(risk))
            catalyst  = np.sign(catalyst) * np.log1p(abs(catalyst))
            
            return sentiment, risk, catalyst
        except Exception:
            return 0.0, 0.0, 0.0

    def predict_conviction(self, symbol: str, xgb_prob: float, kronos_prob: float, hmm_state: str, faiss_sim: float) -> float:
        """
        Calculates the Meta-Conviction ($P$) with Fundamental Macro Integration.
        Returns a probability float [0.0, 1.0].
        """
        # 1. Fetch Deep Research Context (with Dampener)
        macro_sent, black_swan_risk, catalyst = self._get_macro_context(symbol)

        # 2. Hard Override Rule (Phase 6 - Black Swan Protocol)
        if black_swan_risk > 0.85:
            logger.critical(f"[BLACK_SWAN_OVERRIDE] Systemic risk detected ({black_swan_risk:.2f}). Forcing P=0.0")
            return 0.0

        hmm_encoded = self._encode_hmm(hmm_state)
        
        # Feature Array (v18.9 Extended - 7 Features):
        # [XGB, Kronos, HMM, FAISS, Macro_Sent, Macro_Risk, Catalyst]
        X_live = np.array([[
            float(xgb_prob), 
            float(kronos_prob), 
            float(hmm_encoded), 
            float(faiss_sim),
            float(macro_sent),
            float(black_swan_risk),
            float(catalyst)
        ]])
        
        try:
            # Predict using Regressor (continuous [0, 1])
            prediction = self.model.predict(X_live)[0]
            conviction = float(np.clip(prediction, 0.0, 1.0))
            
            logger.info(f"[META-MODEL] {symbol} prediction: {conviction:.6f}")
            return conviction
        except Exception as e:
            logger.error(f"[META-MODEL] Prediction failed: {e}. Defaulting to 0.500.")
            return 0.500

    def train_from_diagnostics(self):
        """
        Trains the Meta-Model with the 7-feature v19.1 vector (Z-score aware).
        """
        logger.info("[META-MODEL] Beginning 7-feature training sequence (SRE Z-Score Mode)...")
        
        X_train = []
        y_train = []
        
        # -- SRE Bootstrap: Inject Synthetic "Perfect Setups" (Z-Scored) ----------
        # Features: [Z_XGB, Z_Kronos, HMM, FAISS, Macro_Sent, Macro_Risk, Catalyst]
        # In Z-score space, 0.85 prob becomes approx +2.0 sigma
        for _ in range(50):
            # Perfect Long (+2.0 sigma tech)
            X_train.append([2.15, 2.05, 1, 0.90, 0.5, 0.1, 0.4]) 
            y_train.append(1)
            # Systemic Anomaly (+3.5 sigma)
            X_train.append([3.5, 3.5, 1, 0.95, 0.6, 0.1, 0.5])
            y_train.append(1)
            # Good Long (+1.2 sigma tech)
            X_train.append([1.35, 1.25, 1, 0.85, 0.3, 0.2, 0.3])
            y_train.append(0.85) 
            # Perfect Short (-2.0 sigma tech)
            X_train.append([-2.15, -2.05, -1, 0.88, -0.5, 0.1, -0.4]) 
            y_train.append(1)
            # Systemic Short Anomaly (-3.5 sigma)
            X_train.append([-3.5, -3.5, -1, 0.95, -0.6, 0.1, -0.5])
            y_train.append(1)
            # Good Short (-1.2 sigma tech)
            X_train.append([-1.35, -1.25, -1, 0.85, -0.3, 0.2, -0.3])
            y_train.append(0.85)
            # Neutral/Noise (0.0 sigma) -> Label 0.15
            X_train.append([0.0, 0.0, 0, 0.20, 0.0, 0.2, 0.0])
            y_train.append(0.15)
            # High Risk Black Swan
            X_train.append([1.5, 1.5, 1, 0.90, 0.8, 0.95, 0.8])
            y_train.append(0)

        if len(X_train) < 5:
            logger.warning("[META-MODEL] Insufficient training data. Aborting train.")
            return False
            
        X = np.array(X_train)
        y = np.array(y_train)
        
        # Retrain a fresh regressor model
        self.model = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
        self.model.fit(X, y)
        
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, MODEL_PATH)
        
        score = self.model.score(X, y)
        logger.info(f"[META-MODEL] Training complete (7 features). Samples: {len(X)}. R^2 Score: {score:.2f}")
        return True

        # -- SRE Bootstrap: Inject Synthetic "Perfect Setups" (Phase 6) --------
        # This prevents the "Zero-Positive" trap where the model only learns '0'.
        # We inject 10 samples representing ideal oracle/regime alignment.
        for _ in range(10):
            # Perfect Long
            X_train.append([0.85, 0.82, 1, 0.90]) # [XGB, Kronos, HMM_BULL, FAISS]
            y_train.append(1)
            # Perfect Short
            X_train.append([0.15, 0.18, -1, 0.88]) # [XGB, Kronos, HMM_BEAR, FAISS]
            y_train.append(1)
            # Noisy Range
            X_train.append([0.50, 0.50, 0, 0.20])
            y_train.append(0)

        if len(X_train) < 5:
            logger.warning("[META-MODEL] Insufficient training data. Aborting train.")
            return False
            
        X = np.array(X_train)
        y = np.array(y_train)
        
        # Retrain a fresh model
        self.model = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42)
        self.model.fit(X, y)
        
        # Ensure data directory exists
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, MODEL_PATH)
        
        score = self.model.score(X, y)
        logger.info(f"[META-MODEL] Training complete. Samples: {len(X)}. Accuracy: {score:.2f}")
        return True

if __name__ == "__main__":
    # Test execution
    mm = MathMetaModel()
    mm.train_from_diagnostics()
    p = mm.predict_conviction(0.85, 0.90, "BULL", 0.88)
    print(f"Test Conviction: {p:.4f}")
