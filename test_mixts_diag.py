"""
MixTS Integration Diagnostic
Verifies that vantage_execute.py can properly sample MixTS weights and belief priors.
"""
import sys
import os
# Mock MT5 if necessary, but we just want to see if the imports and logic work.
try:
    import vantage_execute as ve
    print("[DIAG] Imports successful.")
    
    # Check if MixTS Agent loads
    import gitagent_mixts as mixts
    agent = mixts.MixTSAgent()
    s, theta, priors = agent.sample_regime_and_weights()
    print(f"[DIAG] MixTS Sample: Regime={s}, PriorSum={sum(priors):.2f}")
    
    # Check Synthesis integration
    import gitagent_synthesis as syn
    feats = {"W_rsi": 0.5, "Wy_trend": 0.3}
    mixts_weights = {mixts.FEATURE_KEYS[i]: theta[i] for i in range(len(mixts.FEATURE_KEYS))}
    score = syn.monolithic_score(syn.kernel_transform(feats), mixts_weights=mixts_weights)
    print(f"[DIAG] Sample Score with MixTS: {score:.2f}")
    
    print("[DIAG] MixTS INTEGRATION VERIFIED.")
except Exception as e:
    print(f"[DIAG] INTEGRATION FAILED: {e}")
    import traceback
    traceback.print_exc()
