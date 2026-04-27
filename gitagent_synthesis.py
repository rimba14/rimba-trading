import numpy as np
import torch
import gitagent_timesfm_adapter as tfm
import gitagent_timesnet as tnet
import gitagent_wavelet as wave
from gitagent_base import BaseModule
from typing import Dict, Any, List
import time

class RepresentationLayer(BaseModule):
    """
    Sentinel Representation Layer (Layer 2)
    Responsibility: TimesNet 2D Mapping -> Multi-resolution Feature Tensors.
    Input: Perception dict (Layer 1 output)
    Output: np.ndarray (Flattened feature tensor)
    """
    def __init__(self):
        super().__init__("Representation")
        self.model = tnet.TimesNetPerception(enc_in=5, d_model=64, top_k=3, seq_len=128)

    def process(self, perception_data: Dict[str, Any]) -> Dict[str, Any]:
        ohlcv_df = perception_data.get('ohlcv_df')
        if ohlcv_df is None or len(ohlcv_df) < 128:
            return {"feature_tensor": np.zeros(89), "status": "insufficient_window"}

        f = {}
        
        # ─── 0-63: TimesNet ───
        tn_features, anomaly_score = tnet.get_timesnet_features(ohlcv_df, self.model)
        if tn_features is not None:
            for i in range(len(tn_features)):
                f[f'tn_{i}'] = tn_features[i]
        else:
            for i in range(64): f[f'tn_{i}'] = 0.0
        
        # ─── 64-73: Wavelet ───
        close = ohlcv_df['close'].tail(128).values
        mra = wave.extract_mra_features(close)
        for k in ['w_approx','w_det_L1','w_det_L2','w_std_L1','w_std_L2']:
            f[k] = mra.get(k, 0.0)
            
        lob_data = perception_data.get('lob_data', {})
        f['vpin'] = lob_data.get('vpin', 0.0)
        f['cognition_factor'] = perception_data.get('cognition_factor', 0.0)

        # ─── 74-75: Time-MOE (Phase 161) ───
        import gitagent_timemoe_adapter as moe
        moe_bias, moe_expert = moe.get_moe_features(ohlcv_df)
        f['moe_bias'] = moe_bias
        f['moe_expert'] = float(moe_expert)

        # ─── 76-77: Banushev Hybrid (Phase 163) ───
        import gitagent_spectral_denoiser as spec
        import gitagent_sentiment_bridge as sent
        spec_denoise, spec_noise = spec.get_spectral_features(ohlcv_df)
        sent_pulse = sent.get_sentiment_pulse(perception_data.get('symbol', 'UNKNOWN'), ohlcv_df)
        f['spec_denoise'] = spec_denoise
        f['sent_pulse'] = sent_pulse

        # ─── 78-81: Foundation Model Telemetry (Phase 165 - Expanded v142) ───
        f['kronos_prob'] = perception_data.get('kronos_prob', 0.5)
        f['timesfm_p10_dist'] = perception_data.get('timesfm_p10_dist', 0.0)
        f['timesfm_p90_dist'] = perception_data.get('timesfm_p90_dist', 0.0)
        f['hmm_state_active'] = 1.0 if perception_data.get('hmm_state') == "BULL" else \
                               (-1.0 if perception_data.get('hmm_state') == "BEAR" else 0.0)

        # Convert to flat tensor for Layer 3 (Cognition)
        base_keys = [f'tn_{i}' for i in range(64)] + ['w_approx','w_det_L1','w_det_L2','w_std_L1','w_std_L2', 'vpin', 'cognition_factor', 'moe_bias', 'moe_expert', 'sent_pulse', 'spec_denoise']
        telemetry_keys = ['kronos_prob', 'timesfm_p10_dist', 'timesfm_p90_dist', 'hmm_state_active']
        
        tensor_keys = base_keys + telemetry_keys
        tensor = np.array([f.get(k, 0.0) for k in tensor_keys]).astype('float32')
        if len(tensor) < 93:
            tensor = np.pad(tensor, (0, 93 - len(tensor)))

        return {
            "feature_tensor": tensor,
            "anomaly_score": anomaly_score if anomaly_score else 0.0,
            "metadata": {"timestamp": time.time(), "moe_expert": moe_expert, "spec_noise": spec_noise}
        }

def apply_attention_gate(features, mda_scores, vix, cosmic_data, stats):
    """Phase 88 Restoration: Feature-level gating via MDA/VIX integration."""
    if isinstance(features, dict):
        clean_vals = []
        for v in features.values():
            try:
                clean_vals.append(float(v))
            except (ValueError, TypeError):
                continue
        feat_vec = np.array(clean_vals)
    else:
        feat_vec = features
        
    vix_mult = 1.0 + (max(0, vix - 20) / 40.0)
    # Align mda_scores length to features length
    if isinstance(mda_scores, dict):
        clean_mda = []
        for v in mda_scores.values():
            try:
                clean_mda.append(float(v))
            except (ValueError, TypeError):
                continue
        mda_vec = np.array(clean_mda)
    else:
        mda_vec = mda_scores if mda_scores is not None else 1.0
    
    # Pad or slice mda_vec to match feat_vec
    if isinstance(mda_vec, np.ndarray):
        if len(mda_vec) < len(feat_vec):
            mda_vec = np.pad(mda_vec, (0, len(feat_vec) - len(mda_vec)), constant_values=1.0)
        else:
            mda_vec = mda_vec[:len(feat_vec)]
    
    gated = feat_vec * mda_vec
    gated = np.tanh(gated * vix_mult) # Final kernel compression
        
    return gated, stats

def monolithic_score(features, bayes_weights=None, mixts_weights=None):
    """Phase 88 Restoration: Final ensemble score calculation."""
    if isinstance(features, dict):
        features = np.array([float(v) for v in features.values()])
    
    if bayes_weights is None: 
        bayes_weights = np.ones(len(features)) / len(features)
    elif isinstance(bayes_weights, dict):
        bayes_weights = np.array([float(v) for v in bayes_weights.values()])
        
    feat_len = len(features)
    weight_len = len(bayes_weights)
    
    # ─── New Phase 108: Auto-Expansion logic ───
    if weight_len < feat_len:
        # Pad legacy weights with neutral baseline (mean of existing weights)
        pad_val = np.mean(bayes_weights) if weight_len > 0 else (1.0 / feat_len)
        bayes_weights = np.pad(bayes_weights, (0, feat_len - weight_len), constant_values=pad_val)
    elif weight_len > feat_len:
        bayes_weights = bayes_weights[:feat_len]
        
    score = np.dot(features, bayes_weights)
    if mixts_weights:
         score *= mixts_weights.get('regime_mult', 1.0)
    return float(np.clip(score * 100, -100, 100))

def kernel_transform(x, *args, **kwargs):
    """Phase 93: Generalized non-linear feature normalization."""
    # Robustly handles legacy 'interaction_threshold' and other kwargs
    return np.tanh(x)

def calculate_regime_alignment(hurst_data, fft_data, ising_data, signal):
    return 1.0

def extract_features(agent_scores, macro_data=None, ohlcv_df=None, agent_status=None, lob_data=None):
    # Backward compatibility wrapper
    perc = {"ohlcv_df": ohlcv_df, "lob_data": lob_data, "cognition_factor": agent_status.get('cognition_factor', 0.0) if agent_status else 0.0}
    return RepresentationLayer().process(perc)["feature_tensor"]
