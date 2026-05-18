import sys
import time
import json
from pathlib import Path

# Add project root to path
sys.path.append("C:/Sentinel_Project")

print("=== STEP 1: Regenerating macro_state.json with new G8 mocks ===")
import macro_calendar_sync

# Force regeneration
events = macro_calendar_sync.generate_high_fidelity_mocks()
macro_state = {
    "last_sync": int(time.time()),
    "upcoming_events": events
}
data_dir = Path("C:/Sentinel_Project/data")
data_dir.mkdir(parents=True, exist_ok=True)
with open(data_dir / "macro_state.json", "w", encoding="utf-8") as f:
    json.dump(macro_state, f, indent=4)
print(f"Successfully generated {len(events)} mock events in macro_state.json.")

print("\n=== STEP 2: Testing Liquidity-Tiered Horizons in fastapi_sniper ===")
import fastapi_sniper

# Print the dynamic tiers dictionary
print("Defined Tiers in fastapi_sniper:")
for k, v in fastapi_sniper.MACRO_BLACKOUT_TIERS.items():
    print(f"  {k}: {v} hours")

# Let's perform simulated audits for different symbols:
test_cases = [
    # Majors / Tier 1 (12h limit)
    ("EURUSD", "EURUSD (Tier 1 - 12h)"),
    ("USDJPY", "USDJPY (Tier 1 - 12h)"),
    ("GER40", "GER40 (Tier 1 - 12h)"),
    # Minors / Tier 2 (18h limit)
    ("AUDUSD", "AUDUSD (Tier 2 - 18h)"),
    ("USDCAD", "USDCAD (Tier 2 - 18h)"),
    ("USDCHF", "USDCHF (Tier 2 - 18h)"),
    # Crosses / Tier 3 (24h limit)
    ("EURGBP", "EURGBP (Tier 3 - 24h default)"),
    ("CHFJPY", "CHFJPY (Tier 3 - 24h default)"),
]

print("\nRunning simulated Wall 5 Ex-Ante Blackout check:")
for sym, desc in test_cases:
    vetoed, reason = fastapi_sniper.is_wall5_macro_blackout(sym)
    print(f"\nAsset: {desc}")
    print(f"  Vetoed: {vetoed}")
    print(f"  Reason: {reason if vetoed else 'CLEARED (No imminent Tier-1 event within tier blackout)'}")

print("\n=== SRE DIAGNOSTIC COMPLETE ===")
