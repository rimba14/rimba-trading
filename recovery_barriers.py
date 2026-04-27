import MetaTrader5 as mt5
import json
import os

# --- Load Thesis Store ---
THESIS_FILE = "C:\\Sentinel_Project\\position_thesis.json" # Adjust if different
if os.path.exists(THESIS_FILE):
    with open(THESIS_FILE, 'r') as f:
        thesis_store = json.load(f)
else:
    print("No thesis file found.")
    exit()

if not mt5.initialize():
    print("MT5 Init failed")
    exit()

positions = mt5.positions_get()
updated_count = 0

for p in positions:
    ticket_str = str(p.ticket)
    if ticket_str in thesis_store:
        thesis = thesis_store[ticket_str]
        # Check if it was a 'tight' stop (e.g. 1.2x)
        old_barrier = thesis.get('sl_barrier', 0)
        atr = thesis.get('entry_atr', 0)
        
        if atr > 0:
            is_buy = (p.type == mt5.ORDER_TYPE_BUY)
            # Apply new 1.8x Institutional Standard
            new_dist = 1.8 * atr
            new_barrier = p.price_open - new_dist if is_buy else p.price_open + new_dist
            
            # Update only if widening (to prevent accidental tightening)
            if is_buy and new_barrier < old_barrier:
                thesis['sl_barrier'] = new_barrier
                updated_count += 1
            elif not is_buy and new_barrier > old_barrier:
                thesis['sl_barrier'] = new_barrier
                updated_count += 1
                
            print(f"[RECOVERY] {p.symbol} ({p.ticket}): {old_barrier:.5f} -> {thesis['sl_barrier']:.5f}")

# Save back
with open(THESIS_FILE, 'w') as f:
    json.dump(thesis_store, f, indent=4)

print(f"\n[RECOVERY COMPLETE] Updated {updated_count} positions to 1.8x ATR standard.")
