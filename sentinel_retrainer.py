import os
import time
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] RETRAINER: %(message)s")
logger = logging.getLogger("SentinelRetrainer")

# Paths
PROJECT_ROOT = Path(r"C:\Sentinel_Project")
SHAP_DIR = PROJECT_ROOT / "shap_diagnostics"
DATA_DIR = PROJECT_ROOT / "data"
TRADES_LEDGER = PROJECT_ROOT / "trades_ledger.csv"

# Models
MODEL_VNEXT = DATA_DIR / "meta_model_vNext.pkl"
MODEL_ACTIVE = DATA_DIR / "meta_model_active.pkl"

class ContinuousRetrainer:
    def __init__(self, model_type="random_forest"):
        self.model_type = model_type
        self.lookback_days = 30
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
    def gather_data(self):
        """
        Pulls the last 30 days of feature data and applies v19.2 transformations.
        """
        logger.info(f"Gathering data for the last {self.lookback_days} days...")
        X, y = [], []
        cutoff_date = datetime.now() - timedelta(days=self.lookback_days)
        
        if SHAP_DIR.exists():
            for d_file in SHAP_DIR.glob("*.json"):
                if datetime.fromtimestamp(d_file.stat().st_mtime) < cutoff_date:
                    continue
                try:
                    with open(d_file, 'r') as f:
                        data = json.load(f)
                    
                    xgb_prob = data.get("xgboost_prob", 0.5)
                    kronos_prob = data.get("kronos_prob", 0.5)
                    hmm_state_raw = data.get("hmm_state", "RANGE")
                    hmm_state_encoded = 1 if hmm_state_raw == "BULL" else (-1 if hmm_state_raw == "BEAR" else 0)
                    faiss_sim = data.get("faiss_similarity_score", 0.5)
                    macro_sent = data.get("macro_sentiment", 0.0)
                    macro_risk = data.get("macro_risk", 0.0)
                    catalyst = data.get("catalyst", 0.0)

                    # v19.2 Transformations
                    macro_sent = np.sign(macro_sent) * np.log1p(abs(macro_sent))
                    macro_risk = np.sign(macro_risk) * np.log1p(abs(macro_risk))
                    catalyst   = np.sign(catalyst) * np.log1p(abs(catalyst))
                    z_xgb = (xgb_prob - 0.5) / 0.15 
                    z_kronos = (kronos_prob - 0.5) / 0.15

                    p_final = float(data.get("conviction", 0.5))
                    label = 1 if p_final > 0.80 else 0
                    
                    X.append([z_xgb, z_kronos, hmm_state_encoded, faiss_sim, macro_sent, macro_risk, catalyst])
                    y.append(label)
                except:
                    continue

        # MiroFish Synthetic episodes (50/50 split)
        hist_count = len(X) if len(X) > 0 else 50
        for _ in range(hist_count):
            # Synthetic Long Scenario
            ms, mr, mc = np.log1p(0.5), np.log1p(0.1), np.log1p(0.4)
            zx, zk = (0.85 - 0.5) / 0.15, (0.82 - 0.5) / 0.15
            X.append([zx, zk, 1, 0.90, ms, mr, mc]); y.append(1)
            
            # Synthetic Risk Scenario
            ms, mr, mc = np.log1p(0.8), np.log1p(0.95), np.log1p(0.8)
            zx, zk = (0.90 - 0.5) / 0.15, (0.90 - 0.5) / 0.15
            X.append([zx, zk, 1, 0.90, ms, mr, mc]); y.append(0)
            
        return np.array(X), np.array(y)

    def train_and_validate(self):
        X, y = self.gather_data()
        if len(X) < 10:
            logger.error("Insufficient data for retraining.")
            return False
            
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = RandomForestRegressor(n_estimators=200, max_depth=12, random_state=42)
        model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        acc = np.mean((preds > 0.5) == (y_test > 0.5))
        logger.info(f"Retrained Meta-Model Proxy Accuracy: {acc:.2%}")
        
        if acc > 0.55:
            joblib.dump(model, MODEL_VNEXT)
            logger.info(f"Model saved to {MODEL_VNEXT}")
            return True
        return False

    def hot_swap(self):
        if not MODEL_VNEXT.exists(): return False
        logger.info(f"Hot-swapping {MODEL_ACTIVE.name}...")
        try:
            os.replace(MODEL_VNEXT, MODEL_ACTIVE)
            logger.info("Hot-swap successful.")
            return True
        except Exception as e:
            logger.error(f"Hot-swap failed: {e}")
            return False

if __name__ == "__main__":
    retrainer = ContinuousRetrainer()
    if retrainer.train_and_validate():
        retrainer.hot_swap()
