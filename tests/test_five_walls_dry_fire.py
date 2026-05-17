import requests

BASE = "http://localhost:8000"

test_cases = [
    # (test_name, payload, expected_status, expected_pattern)
    (
        "Ghost Version at Boot",
        "MANUAL_BOOT_CHECK",
        "PASS",  
        None
    ),
    (
        "RANGE Regime Momentum Block",
        {"symbol": "EURUSD", "direction": "BUY", "conviction": 0.85, 
         "hmm_state": "RANGE", "rsi": 55.0, "alpha_features": {"P": 0.85, "atr": 0.001, "regime": "RANGE"}},
        "rejected",
        "Pattern 1"
    ),
    (
        "Phantom Conviction Block",
        {"symbol": "EURUSD", "direction": "BUY", "conviction": 0.52, 
         "hmm_state": "BULL", "rsi": 45.0, "alpha_features": {}},
        "rejected",
        "Pattern 2"
    ),
    (
        "Empty Alpha Features Warning",
        {"symbol": "EURUSD", "direction": "BUY", "conviction": 0.82, 
         "hmm_state": "BULL", "rsi": 45.0, "alpha_features": {}},
        "rejected",  
        "Pattern 4"
    ),
    (
        "Valid RANGE Mean Reversion Trade",
        {"symbol": "EURUSD", "direction": "BUY", "conviction": 0.82, 
         "hmm_state": "RANGE", "rsi": 30.0, 
         "alpha_features": {"P": 0.82, "atr": 0.0005, "regime": "RANGE", "order_flow_entropy": 0.75}},
        "success",  
        None
    ),
]

print("=== FIVE WALLS DRY FIRE TEST ===\n")
all_pass = True

for test_name, payload, expected_status, expected_pattern in test_cases:
    if payload == "MANUAL_BOOT_CHECK":
        try:
            import sys
            from pathlib import Path
            sys.path.append(str(Path(__file__).parent.parent))
            from sentinel.version_manifest import AGENT_SIGNATURE
            result = "PASS" if "v" in AGENT_SIGNATURE else "FAIL"
            print(f"{'[OK]' if result == 'PASS' else '[FAIL]'} {test_name}: {AGENT_SIGNATURE}")
        except ImportError:
            print(f"[FAIL] {test_name}: AGENT_SIGNATURE could not be imported.")
            all_pass = False
        continue

    try:
        resp = requests.post(f"{BASE}/execute_trade", json=payload).json()
        status_ok = resp.get('status') == expected_status
        pattern_ok = expected_pattern is None or expected_pattern in resp.get('reason', '')
        passed = status_ok and pattern_ok
        all_pass = all_pass and passed
        icon = "[OK]" if passed else "[FAIL]"
        
        print(f"{icon} {test_name}")
        if not passed:
            print(f"     Expected: status={expected_status} pattern={expected_pattern}")
            print(f"     Got:      status={resp.get('status')} reason={resp.get('reason','')[:80]}")
    except requests.exceptions.ConnectionError:
        print(f"[CRITICAL FAIL] Connection Refused. Is fastapi_sniper.py running on port 8000?")
        all_pass = False
        break

print(f"\n{'ALL TESTS PASSED - WALLS ARE IRONCLAD' if all_pass else 'SOME TESTS FAILED - CHECK LOGS'}")
import sys
sys.exit(0 if all_pass else 1)
