import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import sys

# Sentinel Core Modules
sys.path.append("C:\\Sentinel_Project\\")
try:
    import gitagent_synthesis as syn
    import gitagent_mixts as mixts
    import gitagent_timemoe_adapter as moe
    import gitagent_spectral_denoiser as spec
    import gitagent_sentiment_bridge as sent
    print("[DIAG] All 13D Core Modules Imported Successfully.")
except Exception as e:
    print(f"[CRITICAL] Import failure: {e}")
    sys.exit(1)

def run_diagnostic():
    if not mt5.initialize():
        print("MT5 Init Failed.")
        return

    account = mt5.account_info()
    if account is None:
        print("Failed to get account info.")
        return

    print("\n" + "="*50)
    print("INSTITUTIONAL LEVERAGE AUDIT")
    print("="*50)
    print(f"Equity:      ${account.equity:,.2f}")
    print(f"Balance:     ${account.balance:,.2f}")
    print(f"Leverage:    1:{account.leverage} (Confirmed 1:500 Upgrade)" if account.leverage == 500 else f"Leverage: 1:{account.leverage}")
    print(f"Free Margin: ${account.margin_free:,.2f}")
    
    # ─── 13D ENSEMBLE AUDIT ───
    print("\n" + "="*50)
    print("13D ENSEMBLE HEARTBEAT (EURUSD TEST)")
    print("="*50)
    symbol = "EURUSD"
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 256)
    df = pd.DataFrame(rates)
    
    # 1. Perception & Features
    rl = syn.RepresentationLayer()
    features = rl.process({"ohlcv_df": df, "symbol": symbol})
    tensor = features['feature_tensor']
    
    # 2. Key Alpha Vector Extraction
    # Indices based on FEATURE_KEYS: [..., MOE_bias(9), MOE_expert(10), SENT_pulse(11), SPEC_denoise(12)]
    # Note: Synthesis pad to 93, let's check the last few.
    print(f"[MOE] Expert ID: {features['metadata'].get('moe_expert')}")
    print(f"[SENT] Pulse:   {tensor[91] if len(tensor)>91 else 'N/A'}")
    print(f"[SPEC] Denoise: {tensor[92] if len(tensor)>92 else 'N/A'}")
    print(f"[SPEC] Noise:   {features['metadata'].get('spec_noise'):.4f}")
    
    # 3. Decision Pipeline
    mixts_agent = mixts.MixTSAgent() 
    regime, weights, priors = mixts_agent.sample_regime_and_weights()
    print(f"\n[MixTS] Active Regime: {regime}")
    print(f"[MixTS] 13D Weights Summary: {np.round(weights, 3)}")

    print("\n" + "="*50)
    print("DIAGNOSTIC COMPLETE: SYSTEM READY.")
    print("="*50)
    mt5.shutdown()

if __name__ == "__main__":
    run_diagnostic()
