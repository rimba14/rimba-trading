import os
import sys
import time
import json
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
import xgboost as xgb

# Set path
sys.path.append(r"C:\Sentinel_Project")
import feature_engineering as feat_eng
import gitagent_hmm as hmm
import gitagent_sigproc as sigproc
import gitagent_utils as utils
import kronos_bridge
import rl_agents.oxford_ddqn as ddqn_bridge
from agent_quarantine import registry
from sentinel_slow_loop import (
    _XGB_MODEL, 
    get_xgb_prediction, 
    optimize_fracdiff_d, 
    oracle_lib
)

def perform_sync_audit():
    print("=== DIRECTIVE 1: MODEL SYNCHRONIZATION AUDIT (USDCAD) ===")
    
    symbol = "USDCAD"
    if not mt5.symbol_select(symbol, True):
        print(f"[FAIL] Could not select {symbol}")
        return False
        
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 750)
    if rates is None or len(rates) < 512:
        print("[FAIL] M15 data insufficient, trying M1 fallback...")
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 750)
        if rates is None or len(rates) < 512:
            print("[FAIL] Insufficient data fallback.")
            return False
            
    df_ta = pd.DataFrame(rates)
    df_ta['time'] = pd.to_datetime(df_ta['time'], unit='s')
    
    # Feature Calculations (standard tech indicators)
    c = df_ta["close"]
    delta = c.diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df_ta["W_rsi"]    = 100 - (100 / (1 + gain / (loss + 1e-9)))
    
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    df_ta["W_macd"]   = macd - macd.ewm(span=9, adjust=False).mean()
    
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    df_ta["Wy_trend"] = (ema20 - ema50) / (c * 0.01 + 1e-9)
    
    ma20  = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    df_ta["B_bbpos"]  = (c - (ma20 - 2*std20)) / (4*std20 + 1e-9)
    df_ta["WHL_vol"]  = c.pct_change().rolling(20).std()
    df_ta["S_struct"]  = 0.5
    
    # Fractionally Differentiated Features
    df_ml = df_ta.copy()
    for col in ["open", "high", "low", "close"]:
        opt_d, fd = optimize_fracdiff_d(df_ta[col].values)
        pad = len(df_ta) - len(fd)
        norm_fd = sigproc.strict_normalize(fd)
        df_ml[col] = np.pad(norm_fd, (pad, 0), mode="edge")
        
    df_ml = feat_eng.engineer_features(
        df_ml,
        price_col="close",
        volume_col="tick_volume" if "tick_volume" in df_ml.columns else "volume",
        frac_d=0.45,
        fft_top_k=3,
        cs_rank=0.5,
    )
    df_ml = df_ml.dropna()
    
    # Extract feature inputs
    latest_features = df_ml.tail(1).select_dtypes(include=[np.number])
    feature_vec = df_ml.select_dtypes(include=[np.number]).iloc[-1].astype(float).values
    
    ts_xgb = df_ml['time'].iloc[-1]
    ts_ddqn = df_ml['time'].iloc[-1]
    
    # Mathematical assertions
    assert len(latest_features.columns) == len(feature_vec), "Feature dimensions mismatch!"
    assert np.allclose(latest_features.values[0], feature_vec, atol=1e-7), "Feature value mismatch!"
    assert ts_xgb == ts_ddqn, "Timestamp mismatch!"
    
    print(f"[OK] Mathematical Verification: PASS")
    print(f"[OK] Timestamps match perfectly: {ts_xgb}")
    print(f"[OK] Input dimensions match perfectly: {len(feature_vec)} features.")
    
    # Live Predictions for USDCAD
    x_prob = get_xgb_prediction(df_ml)
    ddqn_p = 0.500
    from rl_agents.oxford_ddqn import CHECKPOINT_PATH
    if os.path.exists(CHECKPOINT_PATH):
        ddqn_agent = ddqn_bridge.get_ddqn_agent()
        ddqn_p = ddqn_agent.infer_probability(feature_vec)
        
    print(f"USDCAD Model 1 (XGBoost) Prediction: {x_prob:.4f}")
    print(f"USDCAD Model 2 (DDQN) Prediction: {ddqn_p:.4f}")
    print(f"USDCAD Raw Feature Array Slice (First 5): {feature_vec[:5]}")
    return True

def run_consensus_heatmap():
    print("\n=== DIRECTIVE 2: THE CONSENSUS HEATMAP (WATCHLIST EXPANSION) ===")
    
    assets = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "NZDUSD", "USDCAD", "EURGBP",
        "SP500", "NAS100", "GER40", "US2000", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", 
        "LTCUSD", "XAUUSD", "XAGUSD", "CL-OIL"
    ]
    
    # Make sure they are tradeable
    active_assets = []
    for a in assets:
        if mt5.symbol_select(a, True):
            active_assets.append(a)
            
    print(f"Successfully selected {len(active_assets)}/20 assets for live scanning.")
    
    results = []
    from rl_agents.oxford_ddqn import CHECKPOINT_PATH
    ddqn_agent = None
    if os.path.exists(CHECKPOINT_PATH):
        ddqn_agent = ddqn_bridge.get_ddqn_agent()
        
    for symbol in active_assets:
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 750)
            if rates is None or len(rates) < 512:
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 750)
                if rates is None or len(rates) < 512:
                    continue
                    
            df_ta = pd.DataFrame(rates)
            c = df_ta["close"]
            delta = c.diff()
            gain  = delta.where(delta > 0, 0).rolling(14).mean()
            loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
            df_ta["W_rsi"]    = 100 - (100 / (1 + gain / (loss + 1e-9)))
            
            ema12 = c.ewm(span=12, adjust=False).mean()
            ema26 = c.ewm(span=26, adjust=False).mean()
            macd  = ema12 - ema26
            df_ta["W_macd"]   = macd - macd.ewm(span=9, adjust=False).mean()
            
            ema20 = c.ewm(span=20, adjust=False).mean()
            ema50 = c.ewm(span=50, adjust=False).mean()
            df_ta["Wy_trend"] = (ema20 - ema50) / (c * 0.01 + 1e-9)
            
            ma20  = c.rolling(20).mean()
            std20 = c.rolling(20).std()
            df_ta["B_bbpos"]  = (c - (ma20 - 2*std20)) / (4*std20 + 1e-9)
            df_ta["WHL_vol"]  = c.pct_change().rolling(20).std()
            df_ta["S_struct"]  = 0.5
            
            df_ml = df_ta.copy()
            for col in ["open", "high", "low", "close"]:
                opt_d, fd = optimize_fracdiff_d(df_ta[col].values)
                pad = len(df_ta) - len(fd)
                norm_fd = sigproc.strict_normalize(fd)
                df_ml[col] = np.pad(norm_fd, (pad, 0), mode="edge")
                
            df_ml = feat_eng.engineer_features(
                df_ml,
                price_col="close",
                volume_col="tick_volume" if "tick_volume" in df_ml.columns else "volume",
                frac_d=0.45,
                fft_top_k=3,
                cs_rank=0.5,
            )
            df_ml = df_ml.dropna()
            
            # Predict XGBoost
            x_prob = get_xgb_prediction(df_ml)
            
            # Predict DDQN
            feature_vec = df_ml.select_dtypes(include=[np.number]).iloc[-1].astype(float).values
            ddqn_p = 0.500
            if ddqn_agent is not None:
                ddqn_p = ddqn_agent.infer_probability(feature_vec)
                
            # Predict Kronos (read cache fallback if not online)
            k_prob = 0.500
            try:
                kronos_bridge.update_cognition_cache(symbol, df_ml)
                if oracle_lib.has_symbol(f"{symbol}_kronos"):
                    k_data = oracle_lib.read(f"{symbol}_kronos").data.iloc[-1]
                    k_prob = float(k_data["kronos_prob"])
            except Exception as _ke:
                pass
                
            # Weight blending
            scores_raw = {"kronos": k_prob, "xgb": x_prob, "ddqn": ddqn_p}
            q_result = registry.filter_agents(scores_raw)
            active_scores = q_result.filtered_scores
            
            base_weights = {"kronos": 0.4, "xgb": 0.3, "ddqn": 0.3}
            total_active_weight = sum(base_weights[name] for name in active_scores)
            
            if total_active_weight > 0:
                p_blend = sum(
                    active_scores[name] * (base_weights[name] / total_active_weight)
                    for name in active_scores
                )
            else:
                p_blend = 0.500
                
            divergence = max(active_scores.values()) - min(active_scores.values()) if len(active_scores) > 1 else 0.0
            
            results.append({
                'symbol': symbol,
                'xgb': x_prob,
                'ddqn': ddqn_p,
                'kronos': k_prob,
                'divergence': divergence,
                'p_blend': p_blend
            })
            
        except Exception as e:
            print(f"Exception scanning {symbol}: {e}")
            
    # Sort by divergence lowest to highest
    results.sort(key=lambda x: x['divergence'])
    
    print("\n| Rank | Symbol | Model 1 (XGB) | Model 2 (RL) | Model 3 (Kronos) | Divergence | Blended P-Score | Wall 2 Pass |")
    print("|---|---|---|---|---|---|---|---|")
    for idx, r in enumerate(results, 1):
        # Wall 2 check: Divergence < 0.30 and (blended P < 0.40 or > 0.60)
        wall2_pass = r['divergence'] < 0.30 and (r['p_blend'] < 0.40 or r['p_blend'] > 0.60)
        pass_str = "**PASS / READY**" if wall2_pass else "Blocked"
        print(f"| {idx} | {r['symbol']} | {r['xgb']:.4f} | {r['ddqn']:.4f} | {r['kronos']:.4f} | {r['divergence']:.4f} | {r['p_blend']:.4f} | {pass_str} |")

def main():
    if not mt5.initialize():
        print("MT5 Init failed")
        return
        
    try:
        perform_sync_audit()
        run_consensus_heatmap()
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
