import json
import math

with open('C:\\Sentinel_Project\\rsi_trade_journal.json', 'r') as f:
    journal = json.load(f)

trades = journal.get("trades", [])
if not trades:
    print("No trades found.")
    exit()

last_50 = trades[-50:]
wins = sum(1 for t in last_50 if str(t.get("outcome")).upper() in ["WIN", "1"])
win_rate = wins / len(last_50)

pnls = [t.get("pnl", t.get("pnl_dollars", 0.0)) for t in last_50]
pnl_mean = sum(pnls) / len(last_50)
pnl_std = math.sqrt(sum((x - pnl_mean)**2 for x in pnls) / len(last_50)) + 1e-9
# sharpe_20 equivalent for 50 trades
sharpe = (pnl_mean / pnl_std) * math.sqrt(len(last_50))

cumulative = 0
peak = 0
dd_max = 0
cons_losses = 0
max_cons = 0

# Full history drawdown for System M
cum_total = 0
peak_total = 0
for t in trades:
    pnl = t.get("pnl", t.get("pnl_dollars", 0.0))
    cum_total += pnl
    if cum_total > peak_total: peak_total = cum_total
    dd = (peak_total - cum_total) / max(1.0, peak_total)
    if dd > dd_max: dd_max = dd

for t in last_50:
    outcome = str(t.get("outcome")).upper()
    if outcome in ["LOSS", "-1"]:
        cons_losses += 1
        max_cons = max(max_cons, cons_losses)
    else:
        cons_losses = 0

print(f"Stats for last {len(last_50)} trades:")
print(f"Win Rate: {win_rate:.1%}")
print(f"Sharpe: {sharpe:.2f}")
print(f"Max DD (Full history): {dd_max:.1%}")
print(f"Max Consecutive Losses (Last 50): {max_cons}")

if dd_max > 0.10 or max_cons >= 5:
    print("STATUS: RECOVER mode triggered.")
else:
    print("STATUS: Mode should be EXPLORE/EXPLOIT.")
