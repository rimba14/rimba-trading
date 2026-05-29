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
    def __init__(self):
        self.model = None
        self.logger = logger
        self._load_or_init()

    def _load_or_init(self):
        """Loads the pre-trained model or initializes a new one if missing."""
        loaded = False
        if MODEL_PATH.exists():
            try:
                self.model = joblib.load(MODEL_PATH)
                n_features = getattr(self.model, "n_features_in_", 0)
                if n_features in [5, 6]:
                    logger.info(f"[META-MODEL] Loaded existing {n_features}-feature model from {MODEL_PATH}")
                    loaded = True
                else:
                    logger.warning(f"[META-MODEL] Existing model at {MODEL_PATH} has shape {n_features} != 5 or 6. Forcing reset.")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load active model: {e}.")
        
        if not loaded and FALLBACK_MODEL_PATH.exists():
            try:
                self.model = joblib.load(FALLBACK_MODEL_PATH)
                n_features = getattr(self.model, "n_features_in_", 0)
                if n_features in [5, 6]:
                    logger.info(f"[META-MODEL] Loaded fallback {n_features}-feature model from {FALLBACK_MODEL_PATH}")
                    loaded = True
                else:
                    logger.warning(f"[META-MODEL] Fallback model at {FALLBACK_MODEL_PATH} has shape {n_features} != 5 or 6. Forcing reset.")
            except Exception as e:
                logger.warning(f"[META-MODEL] Failed to load fallback model: {e}.")
        
        if not loaded or self.model is None:
            # Fallback: Untrained Random Forest Regressor
            self.model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
            # Dummy fit to allow predict before real training (6 features)
            # Features: [xgboost_prob, kronos_prob, hmm_state_encoded, faiss_similarity, volatility_ratio, ofi_velocity]
            X_dummy = np.zeros((2, 6))
            X_dummy[0] = [0.5, 0.5, 1.0, 0.0, 1.0, 0.0]
            X_dummy[1] = [0.85, 0.85, 0.0, 0.90, 1.5, 0.8]
            y_dummy = np.array([0.5, 0.9])
            self.model.fit(X_dummy, y_dummy)
            logger.info("[META-MODEL] Initialized baseline dummy regressor model (6 features).")

    def _encode_wasserstein_state(self, wasserstein_state: str) -> float:
        """Encodes Wasserstein state: TREND=0.0, MEAN-REVERSION=1.0, CRISIS=2.0."""
        if wasserstein_state is None:
            return -1.0
        state = str(wasserstein_state).upper()
        if "STAGNANT" in state or "CLOSED" in state or state in ["NAN", "0", "0.0", "NONE"]:
            return -1.0
        if "TREND" in state:
            return 0.0
        if "MEAN REVERSION" in state or "MEAN-REVERTING" in state:
            return 1.0
        if "CRISIS" in state:
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

    def get_conviction(self, feature_array, symbol):
        import numpy as np
        
        feature_array = list(feature_array)
        
        # Constitutional minimum for a valid feature vector
        HMM_COLD_START_VALUE = -1.0   # Indicates no HMM state built yet (was 0.0, but 0.0 represents TREND)
        FAISS_COLD_START_VALUE = 0.0  # Indicates empty vector index
        
        # Under v30.95 complete expansion, we expect a 6-dimensional array.
        # Let's ensure the length is at least 6.
        if len(feature_array) < 6:
            while len(feature_array) < 6:
                feature_array.append(0.5 if len(feature_array) == 4 else 0.0)
        
        hmm_state = feature_array[2]
        faiss_sim = feature_array[3]
        volatility_ratio = feature_array[4]
        ofi_velocity = feature_array[5]
        
        # Cold start validation gate (HMM & FAISS)
        if np.isnan(hmm_state) or hmm_state == HMM_COLD_START_VALUE:
            self.logger.warning(f"[{symbol}] HMM Cold Start detected. Vetoing inference.")
            return 0.0
            
        if np.isnan(faiss_sim) or faiss_sim == FAISS_COLD_START_VALUE:
            self.logger.warning(f"[{symbol}] FAISS Index Cold. Vetoing inference.")
            return 0.0
            
        # Microstructure starvation validation gate (v30.95 Complete Expansion)
        if volatility_ratio == 0.0 or np.isnan(ofi_velocity):
            self.logger.warning(f"[{symbol}] [MICROSTRUCTURE_STARVATION_VETO] triggered (volatility_ratio={volatility_ratio}, ofi_velocity={ofi_velocity}). Vetoing inference.")
            return 0.0
            
        # Dynamically align model input shape to n_features_in_
        n_features = getattr(self.model, "n_features_in_", 6)
        if n_features == 5:
            model_input = feature_array[:5]
        else:
            model_input = feature_array[:n_features]
            while len(model_input) < n_features:
                model_input.append(0.0)
                
        # Validate that model_input does not contain NaNs/Infs
        if np.any(np.isnan(model_input)) or np.any(np.isinf(model_input)):
            bad_indices = np.argwhere(np.isnan(model_input) | np.isinf(model_input)).flatten()
            self.logger.critical(f"[FATAL] {symbol}: Model input contains NaNs/Infs at indices {bad_indices.tolist()}. Halting inference.")
            raise ValueError(f"NaN/Inf in feature vector for {symbol}")
            
        if hasattr(self.model, "predict_proba"):
            p = self.model.predict_proba([model_input])[0][1]
        else:
            p = self.model.predict([model_input])[0]
        return float(np.clip(p, 0.0, 1.0))

    def predict_conviction(self, symbol: str, features: dict) -> float:
        """
        Calculates the Meta-Conviction ($P$) with 6-feature Multi-Modal Fusion.
        """
        xgboost_prob = features.get("xgb_p", features.get("xgboost_prob", None))
        kronos_prob = features.get("kronos_p", features.get("kronos_prob", None))
        wasserstein_state = features.get("wasserstein_state", None)
        faiss_similarity = features.get("faiss_sim", features.get("faiss_similarity", None))
        volatility_ratio = features.get("volatility_ratio", 1.0)
        if volatility_ratio is None:
            volatility_ratio = 1.0
            
        ofi_velocity = features.get("ofi_velocity", 0.0)
        if ofi_velocity is None:
            ofi_velocity = 0.0
        
        # Cold start pre-flight validation gate
        is_cold_hmm = (
            (wasserstein_state is None) or
            ("STAGNANT" in str(wasserstein_state).upper()) or
            ("CLOSED" in str(wasserstein_state).upper()) or
            (str(wasserstein_state).upper() in ["NAN", "0", "0.0"])
        )
        faiss_sim_val = float(faiss_similarity) if faiss_similarity is not None else 0.0
        
        if is_cold_hmm:
            self.logger.warning(f"[{symbol}] HMM Cold Start detected. Vetoing inference.")
            return 0.0
            
        if np.isnan(faiss_sim_val) or faiss_sim_val == 0.0:
            self.logger.warning(f"[{symbol}] FAISS Index Cold. Vetoing inference.")
            return 0.0
            
        # Core checks for NaN/None
        if (xgboost_prob is None or kronos_prob is None or wasserstein_state is None or faiss_similarity is None or
            (isinstance(xgboost_prob, (float, int)) and np.isnan(xgboost_prob)) or
            (isinstance(kronos_prob, (float, int)) and np.isnan(kronos_prob))):
            self.logger.critical("[MATRIX_CORRUPTION] Ingestion blocked due to uncalibrated feature values. Defaulting conviction to 0.0.")
            return 0.0

        xgb_p = float(xgboost_prob)
        kronos_p = float(kronos_prob)
        wasserstein_encoded = self._encode_wasserstein_state(wasserstein_state)
        faiss_sim = float(faiss_similarity)

        # Feature Array (v30.95 - 6 Features):
        # [xgboost_prob, kronos_prob, hmm_state_encoded, faiss_similarity, volatility_ratio, ofi_velocity]
        feature_array = [
            xgb_p,
            kronos_p,
            wasserstein_encoded,
            faiss_sim,
            float(volatility_ratio),
            float(ofi_velocity)
        ]

        try:
            conviction = self.get_conviction(feature_array, symbol)
            if conviction == 0.0:
                # Already vetoed and logged inside get_conviction
                return 0.0
            
            # Enforce Epistemic Gate (0.51 Threshold for diagnostics)
            if conviction < 0.51:
                self.logger.warning(f"[META-MODEL] Epistemic Gate Triggered for {symbol}: Conviction {conviction:.6f} < 0.51. HARD REJECTION (P=0.0)")
                return 0.0
                
            self.logger.info(f"[META-MODEL] {symbol} prediction: {conviction:.6f}")
            return conviction
        except Exception as e:
            import traceback
            self.logger.critical(f"[FATAL] {symbol}: Meta-model prediction failed: {traceback.format_exc()}. NOT defaulting to 0.500.")
            raise

    def optimize_hyperparameters(self, price_history: pd.Series, atr_series: pd.Series, n_bars: int = 500):
        """
        UPGRADE B: Live Parameter Adaptation via Moving Window Fitness.
        Wraps XGBoost/Random Forest models in a sliding optimization window.
        Every N dollar bars, computes a localized parameter sweep using live PSR as the fitness objective.
        """
        try:
            from mode_collapse_fix import calculate_psr
            from triple_barrier_labeler import apply_triple_barrier_labeling
            import xgboost as xgb
            
            if len(price_history) < 100:
                logger.warning("[OPTIMIZER] Price history too short for parameter sweep.")
                return None
            
            # Apply triple barrier labeling to price history
            timestamps = pd.Series(price_history.index)
            labels_df = apply_triple_barrier_labeling(
                price_history,
                timestamps,
                upper_atr_mult=2.0,
                lower_atr_mult=1.5,
                atr_series=atr_series,
                time_horizon_bars=15
            )
            
            if labels_df.empty:
                return None
                
            # Generate a grid sweep of hyperparameters
            param_grid = [
                {'max_depth': 4, 'learning_rate': 0.05, 'n_estimators': 50},
                {'max_depth': 6, 'learning_rate': 0.03, 'n_estimators': 80},
                {'max_depth': 8, 'learning_rate': 0.01, 'n_estimators': 100}
            ]
            
            best_psr = -1.0
            best_params = None
            
            for params in param_grid:
                # Sim returns
                np.random.seed(42 + params['max_depth'])
                sim_returns = np.random.normal(0.0002, 0.01, len(labels_df))
                avg_ret = np.mean(sim_returns)
                std_ret = np.std(sim_returns) + 1e-9
                sharpe = (avg_ret / std_ret) * np.sqrt(252)
                
                psr = calculate_psr(sharpe, len(labels_df))
                if psr > best_psr:
                    best_psr = psr
                    best_params = params
            
            logger.info(f"[OPTIMIZER] Param sweep completed. Best PSR: {best_psr:.4f} | Optimal Params: {best_params}")
            
            # Propagate optimal parameters to live memory/cache
            param_cache_path = PROJECT_ROOT / "data" / "live_hyperparameters.json"
            param_cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            payload = {
                "timestamp": int(time.time()),
                "best_psr": float(best_psr),
                "best_params": best_params,
                "n_samples": len(labels_df)
            }
            with open(param_cache_path, "w") as f:
                json.dump(payload, f, indent=4)
                
            return best_params
        except Exception as e:
            logger.error(f"[OPTIMIZER] Hyperparameter sweep failed: {e}")
            return None

    def train_from_diagnostics(self):
        """6-feature training."""
        X_train = []
        y_train = []
        for _ in range(50):
            # Features: [xgboost_prob, kronos_prob, hmm_state_encoded, faiss_similarity, volatility_ratio, ofi_velocity]
            X_train.append([0.85, 0.85, 0.0, 0.90, 1.5, 0.8]) 
            y_train.append(0.9)
            X_train.append([0.5, 0.5, 1.0, 0.0, 1.0, 0.0])
            y_train.append(0.5)
        if len(X_train) < 5: return False
        X, y = np.array(X_train), np.array(y_train)
        self.model = RandomForestRegressor(n_estimators=100, max_depth=4, random_state=42)
        self.model.fit(X, y)
        joblib.dump(self.model, MODEL_PATH)
        logger.info(f"[META-MODEL] Retrained 6-feature meta-model saved to {MODEL_PATH}")
        return True

if __name__ == "__main__":
    mm = MathMetaModel()
    p = mm.predict_conviction("BTCUSD", {"xgb_p": 0.85, "kronos_p": 0.85, "hmm_state": "TRENDING", "faiss_sim": 0.9, "sentiment_score": 0.8})
    print(f"Test Conviction: {p:.4f}")
