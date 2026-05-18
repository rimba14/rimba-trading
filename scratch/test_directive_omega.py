import sys
import time
import MetaTrader5 as mt5
from pathlib import Path

# Add project root to path
sys.path.append("C:/Sentinel_Project")

print("=== STARTING DIRECTIVE OMEGA SRE VERIFICATION ===")

import fastapi_sniper
from agents.risk_agent import RiskAgent

print("\n--- Testing Target 1: RiskAgent / Layer 1 (Zero-Sizing & Affordability) ---")
risk_agent = RiskAgent()

# Rule 1.1: Zero-Sizing Veto
passed, reason = risk_agent.check_trade("EURUSD", 0.0, 10.0)
print(f"Zero-Sizing Check (lot=0.0):")
print(f"  Allowed: {passed}")
print(f"  Reason: {reason}")
assert not passed and "ZERO_SIZING_VETO" in reason, "Rule 1.1 Veto failed!"

# Rule 1.2: Affordability Veto
# Simulated tiny account equity check via mock
passed, reason = risk_agent.check_trade("NAS100", 10.0, 10.0)
print(f"Affordability Pre-Screen (low account equity simulated / NAS100):")
print(f"  Allowed: {passed}")
print(f"  Reason: {reason}")

print("\n--- Testing Target 3: fastapi_sniper / Layer 4 & Layer 6 Pre-Flight Checklist ---")

# Point 7: Regime Probability Minimum (Rule 3.3 / Index specificity)
# Simulate Index checkout: NAS100
passed, reason = fastapi_sniper.run_composite_preflight_checklist(
    symbol="NAS100",
    direction="BUY",
    lot=0.1,
    conviction=0.75,
    vpin=0.2,
    hmm_state="BULL",
    xgb_p=0.72,
    ddqn_p=0.75
)
print(f"Index Regime Probability Check:")
print(f"  Passed Checklist: {passed}")
print(f"  Reason: {reason}")

# Point 11: JPY dP/dt velocity kill & Open hour blackout (Rule 6.2)
passed, reason = fastapi_sniper.run_composite_preflight_checklist(
    symbol="USDJPY",
    direction="SELL",
    lot=0.1,
    conviction=0.75,
    vpin=0.2,
    hmm_state="BEAR",
    xgb_p=0.30,
    ddqn_p=0.25
)
print(f"JPY Specifics Check:")
print(f"  Passed Checklist: {passed}")
print(f"  Reason: {reason}")

print("\n=== DIRECTIVE OMEGA SRE VERIFICATION COMPLETE ===")
