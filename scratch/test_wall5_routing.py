import sys
import os
from pathlib import Path
sys.path.append(r"C:\Sentinel_Project")

from fastapi_sniper import is_wall5_macro_blackout

print("====================================================")
print("   SRE WALL 5 CURRENCY-SPECIFIC BLACKOUT TESTING    ")
print("====================================================")

# Symbols under review
test_symbols = [
    "EURUSD",  # G8 Currencies base/quote
    "GBPUSD",  # BOE or FOMC imminent
    "USDJPY",  # BOJ or FOMC imminent
    "AUDCAD",  # RBA or BOC imminent
    "NZDCHF",  # RBNZ or SNB imminent
    "XAUUSD",  # Metals ( USD override exception )
    "NAS100",  # Index ( USD base mapping )
    "GER40"    # Index ( EUR base mapping )
]

for sym in test_symbols:
    is_vetoed, reason = is_wall5_macro_blackout(sym)
    if is_vetoed:
        print(f"❌ [VETOED]  {sym:<8} : {reason}")
    else:
        print(f"✅ [PASSED]  {sym:<8} : No conflicting imminent events. Passed Wall 5.")
print("====================================================")
