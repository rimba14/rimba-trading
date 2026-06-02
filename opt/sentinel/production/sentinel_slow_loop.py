import numpy as np
import pandas as pd
import json
import os

# DEFINE THE TRUST GATE THRESHOLD
WASSERSTEIN_MAX_THRESHOLD = 0.65

def logit(p):
    p = np.clip(p, 1e-5, 1.0 - 1e-5)
    return np.log(p / (1.0 - p))

def hot_load_qlib_alpha_registry(path="/opt/sentinel/shared_alpha_registry/alphas_optimized.json"):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def compute_decoupled_alpha_vector(df, registry):
    alpha_features = []
    for alpha_id, meta in registry.items():
        formula = meta["formula"]
        try:
            if "Ref($close, 5)" in formula:
                df[alpha_id] = df["close"].shift(5)
            elif "Mean($close, 10)" in formula:
                df[alpha_id] = df["close"].rolling(window=10).mean()
            elif "Std($close, 20)" in formula:
                df[alpha_id] = df["close"].rolling(window=20).std()
            elif "Delta($close, 1)" in formula:
                df[alpha_id] = df["close"].diff(1)
            else:
                continue
            df[alpha_id] = df[alpha_id].ffill().bfill()
            alpha_features.append(alpha_id)
        except Exception:
            continue
    return df, alpha_features

def compute_enhanced_faiss_score(raw_faiss_matches, current_wasserstein):
    """
    Applies an exponential time decay and a structural regime distance penalty
    to raw vector retrieval historical matches.
    """
    weighted_scores = []
    total_weight = 0.0
    
    for match in raw_faiss_matches:
        # match structure: {"similarity": float, "delta_t_bars": int, "historic_wasserstein": float}
        sim = match["similarity"]
        dt = match["delta_t_bars"]
        hist_w = match["historic_wasserstein"]
        
        w_time = np.exp(-0.002 * dt)
        w_regime = 1.0 / (1.0 + abs(hist_w - current_wasserstein))
        combined_weight = w_time * w_regime
        
        weighted_scores.append(sim * combined_weight)
        total_weight += combined_weight
        
    return float(np.sum(weighted_scores) / total_weight) if total_weight > 0 else 0.5

def compile_sentinel_multi_modal_vector(market_df, raw_faiss_matches, runtime_state):
    """
    Builds the mathematical multi-modal tracking array and executes trust gate structural checks.
    """
    # 1. Evaluate the Hard Wasserstein Epistemic Trust Gate
    w_state = runtime_state["wasserstein_state"]
    if w_state > WASSERSTEIN_MAX_THRESHOLD:
        print(f"[EPISTEMIC_GATE_TRIGGERED]: Live distribution distance ({w_state}) exceeds maximum verification limit.")
        return None, True # Returns anomaly signal flag
        
    # 2. Extract internal analytical inputs
    sentiment = market_df["sentiment_score"].iloc[-1]
    kronos_prob = market_df["kronos_prob"].iloc[-1]
    xgboost_prob = market_df["xgboost_prob"].iloc[-1]
    
    # 3. Compute Sentiment Cross-Asset Divergence Tension Metric
    sentiment_divergence_delta = abs(logit(sentiment) - logit(kronos_prob))
    market_df["sentiment_divergence_delta"] = sentiment_divergence_delta
    
    # 4. Integrate Analog Memory Metrics
    faiss_calibrated = compute_enhanced_faiss_score(raw_faiss_matches, w_state)
    market_df["faiss_similarity_calibrated"] = faiss_calibrated
    
    # 5. Parse Dynamic Offline Formulas
    registry = hot_load_qlib_alpha_registry()
    market_df, dynamic_alphas = compute_decoupled_alpha_vector(market_df, registry)
    
    # 6. Unify feature structures
    base_features = ["xgboost_prob", "kronos_prob", "sentiment_divergence_delta", "faiss_similarity_calibrated"]
    feature_mask = base_features + dynamic_alphas
    
    feature_vector = market_df[feature_mask].iloc[-1].to_numpy()
    
    # Clean check to ensure arrays contain no corrupted numeric elements
    if not np.isfinite(feature_vector).all():
        return None, True
        
    return feature_vector, False
