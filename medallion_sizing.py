import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import os

# Model Paths
MODEL_PATH = "C:\\Sentinel_Project\\medallion_model.json"
FEATURE_KEYS = ['W_rsi', 'W_macd', 'Wy_trend', 'B_bbpos', 'S_struct', 'WHL_vol', 'COSMO_geoAp', 'COSMO_lunar', 'COSMO_align']

_ML_MODEL = None

def _get_ml_model():
    global _ML_MODEL
    if _ML_MODEL is None and os.path.exists(MODEL_PATH):
        try:
            import xgboost as xgb
            _ML_MODEL = xgb.XGBClassifier()
            _ML_MODEL.load_model(MODEL_PATH)
        except:
            _ML_MODEL = None
    return _ML_MODEL

# Constants 
MAX_TOTAL_POSITIONS = 30
MAX_POS_PER_GROUP = 5
RISK_BUDGET_PCT = 0.02  # Maximum absolute risk for a single idea
KELLY_FRACTION = 0.25   # Quarter Kelly fraction 
MAX_ACCOUNT_RISK_CAP = 0.20 # Enforced: 20% Total Portfolio Heat Cap

def get_dynamic_risk_params():
    params = {"kelly_fraction": KELLY_FRACTION}
    try:
        import json
        with open("C:/Sentinel_Project/dynamic_risk_params.json", "r") as f:
            data = json.load(f)
            if "kelly_fraction" in data: params["kelly_fraction"] = float(data["kelly_fraction"])
    except Exception:
        pass
    return params

ASSET_GROUPS = {
    "FX_MAJOR": ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF"],
    "FX_CROSS": ["GBPJPY", "EURJPY", "EURGBP", "AUDJPY", "NZDUSD"],
    "METALS": ["XAUUSD", "XAGUSD", "GOLD", "SILVER", "XPTUSD", "XPDUSD"],
    "INDICES": ["NAS100", "US30", "SPX500", "SP500", "GER40", "NAS100.r"],
    "ENERGY": ["USOIL", "UKOIL", "CL-OIL", "BRENT"]
}

def get_asset_group(symbol):
    s = symbol.upper()
    for g, syms in ASSET_GROUPS.items():
        if s in syms: return g
    return "MISC"

def calculate_hcs(df, sentiment_score):
    """
    Primary Model: Purely structural Trade Permission Score (TPS/HCS).
    Max score is now 4. ML probability has been stripped out to ensure pure meta-labeling.
    """
    hcs = 0
    
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    
    price_cur = df['close'].iloc[-1]
    macd_cur = macd.iloc[-1]
    sig_cur = signal.iloc[-1]
    
    # 1. Momentum Check
    if (price_cur > ema50 and macd_cur > sig_cur) or (price_cur < ema50 and macd_cur < sig_cur):
        hcs += 1
        
    # 2. Mean-Reversion Check 
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    
    if (rsi < 30) or (rsi > 70):
        hcs += 1
        
    # 3. Regime Check 
    try:
        daily_pct = df['close'].pct_change(window=20).iloc[-1]
        if (daily_pct > 0 and price_cur > ema50) or (daily_pct < 0 and price_cur < ema50):
            hcs += 1
    except: pass
    
    # 4. Sentiment Check 
    if abs(sentiment_score) > 0.2:
        hcs += 1
        
    return hcs

def get_medallion_size(symbol, account_info, atr, hcs, features=None, size_mult=1.0, kronos_prob=None):
    """
    Secondary Model (Meta-Labeling): Institutional Kelly Sizing
    Augmented by Kronos Cognition Bridge (Phase 165)
    Integrated with Conformal Uncertainty & Epistemic Gate (Amendment VII)
    """
    equity = account_info.get('equity', 1000.0)
    
    # Conformal Epistemic Validation check
    features = features or {}
    if features.get("trust_gate_failed", False):
        return {
            "calculated_risk_dollars": 0.0000,
            "kelly_f": 0.0000,
            "win_prob": 0.5,
            "hcs": hcs,
            "trust_gate_failed": True
        }

    # 1. Structural Gate: If the technicals are garbage, block the trade before ML is queried.
    if hcs < 2:
        return {"calculated_risk_dollars": 0.0, "kelly_f": 0.0, "win_prob": 0.0, "hcs": hcs}

    # 2. Extract strictly independent probability (p) from XGBoost
    model = _get_ml_model()
    if model and features:
        try:
            f_df = pd.DataFrame([{k: features.get(k, 0.0) for k in FEATURE_KEYS}])
            p_xgb = float(model.predict_proba(f_df)[0][1])
        except Exception as e:
            import logging
            import traceback
            logging.error(f"CRITICAL INFERENCE FAILURE (XGBoost): {e}")
            logging.error(traceback.format_exc())
            p_xgb = np.nan
    else:
        p_xgb = np.nan

    # 3. Kronos Blending / Override (Layer 3 Cognition)
    if kronos_prob is not None:
        # User defined threshold for full override: 0.65
        if kronos_prob > 0.65 or kronos_prob < 0.35:
            p = kronos_prob
            print(f"[MEDALLION] Kronos Confidence Override: {p:.3f}")
        else:
            # 70/30 Blend
            p = (0.7 * kronos_prob) + (0.3 * p_xgb)
            print(f"[MEDALLION] Cognition Blend: {p:.3f} (Kronos: {kronos_prob:.2f}, XGB: {p_xgb:.2f})")
    else:
        p = p_xgb

    # 4. Risk-Reward Ratio (b)
    b = 1.5 
    q = 1.0 - p
    
    # 5. Dynamic Kelly Formula calculation
    if p <= 0.50:
        f_raw = 0.0  # No mathematical edge, allocate zero capital.
    else:
        f_raw = p - (q / b)
        
    params = get_dynamic_risk_params()
    base_kelly_fraction = params.get("kelly_fraction", KELLY_FRACTION)
    
    # Read Conformal Uncertainty Width & apply scaling penalty
    uncertainty_width = float(features.get("uncertainty_width", 0.0))
    scaling_factor = 1.0
    try:
        import json
        if os.path.exists("C:/Sentinel_Project/dynamic_risk_params.json"):
            with open("C:/Sentinel_Project/dynamic_risk_params.json", "r") as f:
                data = json.load(f)
                scaling_factor = float(data.get("uncertainty_scaling_factor", 1.0))
    except Exception:
        pass
        
    final_kelly_fraction = base_kelly_fraction * max(0.0, 1.0 - (uncertainty_width * scaling_factor))
    
    # Phase 4 Action 2: ATR Volatility Scaling
    atr_scalar = 1.0
    if atr > 0.0001:
        # Inverse relationship: smaller size for high volatility, capped at 2x
        atr_scalar = min(2.0, 0.01 / atr)
        
    f_kelly = max(0, f_raw) * final_kelly_fraction * size_mult * atr_scalar
    
    # Enforce the 2% maximum absolute risk cap per idea
    risk_dollars = equity * min(f_kelly, RISK_BUDGET_PCT)
    
    return {
        "calculated_risk_dollars": round(risk_dollars, 4),
        "kelly_f": round(f_kelly, 4),
        "win_prob": round(p, 3),
        "hcs": hcs
    }

def check_portfolio_gates(symbol, current_positions, equity):
    """
    Layer 5: Portfolio Governor 
    Calculates aggregated portfolio heat to protect against correlated blowups.
    """
    if len(current_positions) >= MAX_TOTAL_POSITIONS: 
        return False, "TOTAL_CAP"
    
    group = get_asset_group(symbol)
    group_count = sum(1 for p in current_positions if get_asset_group(p.get('symbol', '')) == group)
    if group_count >= MAX_POS_PER_GROUP: 
        return False, f"GROUP_CAP_{group}"
        
    # 20% HEAT CAP ENFORCEMENT
    # Assumes 'current_positions' is passed as a list of dicts containing the 'risk_dollars' allocated to each trade.
    total_risk_dollars = sum(p.get('risk_dollars', 0.0) for p in current_positions)
    current_heat_pct = total_risk_dollars / equity if equity > 0 else 0
    
    if current_heat_pct >= MAX_ACCOUNT_RISK_CAP:
        return False, f"HEAT_CAP_BREACH_{round(current_heat_pct*100, 1)}%"
        
    # LEVERAGE WALL ENFORCEMENT (10x Max Notional Exposure)
    total_notional = sum(p.get('notional_value', 0.0) for p in current_positions)
    if equity > 0 and (total_notional / equity) > 10.0:
        return False, f"LEVERAGE_WALL_BREACH_{round(total_notional/equity, 1)}x"
    
    return True, "OK"
