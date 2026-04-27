import pandas as pd
import numpy as np
import os
from gitagent_kronos_adapter import get_kronos_forecast
from gitagent_vision_audit import VisionPatternAgent

def run_diagnostic():
    # Load candles from the previously saved output
    df = pd.read_csv("C:/Users/Administrator/.gemini/antigravity/brain/18362d12-a742-4915-93cc-145f90c33c33/.system_generated/steps/579/output.txt")
    df = df.sort_values('time') # Ensure chronological order
    
    symbol = "CL-OIL"
    action = "SELL"
    
    print(f"\n[DIAGNOSTIC] Auditing {symbol} {action} position...")
    
    # 1. Kronos Audit
    k_res = get_kronos_forecast(df)
    print(f"[KRONOS] Bias: {k_res.get('bias', 0.0):+.4f} | Status: {k_res.get('status')}")
    
    # 2. Vision Audit
    v_agent = VisionPatternAgent()
    v_res = v_agent.audit_visual_structure(df, symbol, action)
    print(f"[VISION] Verdict: {v_res.get('vision_verdict')} | Conf: {v_res.get('vision_confidence')}")
    print(f"[REASONING] {v_res.get('vision_rationale')}")

if __name__ == "__main__":
    run_diagnostic()
