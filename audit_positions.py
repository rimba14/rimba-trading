
import sys
import os
import json
import pandas as pd
from gitagent_context_layer import UniversalContextLayer

def audit_portfolio():
    print("=== HYBRID PORTFOLIO HEALTH AUDIT ===")
    
    # Mock some recent market context for the audit
    market_context = {
        "regime": "VOLATILE",  # Assume volatile given current spreads
        "sentiment": "BULLISH_ON_METALS",
        "volatility_index": 22.5
    }
    
    layer = UniversalContextLayer()
    
    # Audit XAGUSD (The Winner)
    print(f"\n[AUDITING XAGUSD - Current Profit: +$45.20]")
    xag_receipt = {
        "symbol": "XAGUSD",
        "trade_info": {"type": "BUY", "entry": 72.074, "tp": 74.55, "sl": 71.084},
        "confidence": 0.92,
        "regime": "STABLE",
        "urgency": "LOW",
        "cognition_factor": 0.85,
        "module_10": {"trend": 1, "smc": 1, "whale": 1},
        "m10_score": 0.0 # No flip
    }
    verdict, reasoning, engine = layer.process(xag_receipt)
    print(f"Verdict: {verdict} | Engine: {engine} | Reasoning: {reasoning}")

    # Audit GBPUSD (The Loser)
    print(f"\n[AUDITING GBPUSD - Current Loss: -$3.89]")
    gbp_receipt = {
        "symbol": "GBPUSD",
        "trade_info": {"type": "BUY", "entry": 1.32356, "tp": 1.32763, "sl": 1.31745},
        "confidence": 0.42,
        "regime": "EXTREME_VOLATILITY",
        "urgency": "HIGH",
        "cognition_factor": 0.35,
        "module_10": {"trend": -1, "smc": -1, "whale": -1},
        "m10_score": 5.5 # Significant flip
    }
    verdict, reasoning, engine = layer.process(gbp_receipt)
    print(f"Verdict: {verdict} | Engine: {engine} | Reasoning: {reasoning}")

if __name__ == "__main__":
    audit_portfolio()
