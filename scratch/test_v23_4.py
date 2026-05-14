import time
import requests
import subprocess
import os
import sys

def test_mutex():
    print("[TEST 1] Starting Mutex Cooldown Test...")
    # Inject an entry directly to simulate a recent trade
    import sys
    sys.path.append(r"C:\Sentinel_Project")
    from fastapi_sniper import entry_cooldowns, execute_trade_endpoint, TradeSignal
    import asyncio
    
    # Simulate first trade
    symbol = "XAUUSD"
    entry_cooldowns[symbol] = time.time()
    
    # Simulate second trade
    signal = TradeSignal(
        symbol=symbol,
        direction="BUY",
        conviction=0.9,
        hmm_state="BULL",
        timestamp=int(time.time())
    )
    
    try:
        asyncio.run(execute_trade_endpoint(signal))
        print("[FAIL] Mutex Test: Second trade was not blocked.")
        return False
    except Exception as e:
        if "429" in str(e) or "cooldown" in str(e).lower():
            print("[PASS] Mutex Test: Second trade successfully blocked by 60s cooldown.")
            return True
        else:
            print(f"[ERROR] Mutex Test: Unexpected error: {e}")
            return False

def test_cumulative_risk():
    print("\n[TEST 2] Starting Cumulative Risk Limit Test...")
    # Using the local RiskAgent class to bypass needing a running server if port is blocked
    import sys
    sys.path.append(r"C:\Sentinel_Project\agents")
    from risk_agent import RiskAgent
    
    agent = RiskAgent()
    # Mock max limit to 250
    agent.max_symbol_exposure_usd = 250.0
    agent.max_position_size_usd = 2000000.0  # Bypass single position limit for test
    
    # Attempt a trade that intentionally exceeds limit
    allow, reason = agent.check_trade("XAUUSD", 1000000.0, 5)
    
    if not allow and ("Exposure" in reason or "Cap Reached" in reason):
        print(f"[PASS] Cumulative Risk Test: Successfully returned VETO (403 condition). Reason: {reason}")
        return True
    else:
        print(f"[FAIL] Cumulative Risk Test: Failed to block trade. Result: allow={allow}, reason={reason}")
        return False

if __name__ == "__main__":
    print("==============================================")
    print(" v23.4 INTEGRITY AUDIT (Mutex & Stateful Risk)")
    print("==============================================")
    
    r1 = test_mutex()
    r2 = test_cumulative_risk()
    
    if r1 and r2:
        print("\n[AUDIT SUCCESS] All v23.4 security locks are holding.")
    else:
        print("\n[AUDIT FAILED] Security locks breached.")
