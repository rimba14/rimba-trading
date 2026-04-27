import sys
import os
import time

def check_imports():
    print("[1/4] Checking Institutional Bridge Imports...")
    bridges = [
        "gitagent_macro_oracle",
        "gitagent_dexter_bridge",
        "gitagent_ai4trade_bridge",
        "gitagent_owl_bridge",
        "gitagent_sentiment_bridge",
        "gitagent_adaptive_sentinel"
    ]
    for b in bridges:
        try:
            __import__(b)
            print(f"  OK: {b}")
        except Exception as e:
            print(f"  FAIL: {b} | Error: {e}")
            return False
    return True

def check_env():
    print("[2/4] Verifying Environment Context...")
    env_path = "C:\\Sentinel_Project\\.env"
    if not os.path.exists(env_path):
        print(f"  FAIL: {env_path} missing.")
        return False
    print(f"  OK: {env_path} found.")
    return True

def dry_run_sentiment():
    print("[3/4] Executing Dry Run Sentiment Pulse...")
    from gitagent_sentiment_bridge import get_sentiment_pulse
    import pandas as pd
    
    # Mock data
    df = pd.DataFrame({'close': [100]*200, 'high': [101]*200, 'low': [99]*200})
    try:
        pulse = get_sentiment_pulse("XAUUSD", df)
        print(f"  OK: Pulse generated: {pulse}")
        return True
    except Exception as e:
        print(f"  FAIL: Sentiment logic error: {e}")
        return False

def check_risk_state():
    print("[4/4] Verifying Sentinel Risk Persistence...")
    state_path = "C:\\Sentinel_Project\\sentinel_risk_state.json"
    if os.path.exists(state_path):
        print(f"  OK: {state_path} active.")
    else:
        print(f"  NOTE: {state_path} will be created on first save.")
    return True

if __name__ == "__main__":
    print("--- SENTINEL PIPELINE INTEGRITY AUDIT ---")
    results = [check_imports(), check_env(), dry_run_sentiment(), check_risk_state()]
    if all(results):
        print("\n[CONCLUSION] SYSTEM NOMINAL: Entry pipelines are operational.")
    else:
        print("\n[CONCLUSION] SYSTEM COMPROMISED: Errors detected in core bridges.")
