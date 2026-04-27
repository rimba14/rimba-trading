import MetaTrader5 as mt5
import datetime

if not mt5.initialize():
    print("MT5 Init Failed")
    exit()

acc = mt5.account_info()
print(f"--- ACCOUNT ---")
if acc:
    print(f"Equity: ${acc.equity:.2f} | Balance: ${acc.balance:.2f} | Margin: ${acc.margin:.2f}")

pos = mt5.positions_get()
print("\n--- OPEN POSITIONS ---")
for p in (pos or []):
    print(f"{p.symbol} | Ticket: {p.ticket} | Vol: {p.volume} | Profit: ${p.profit:.2f} | Open: {p.price_open} | SL: {p.sl} | TP: {p.tp}")

now = datetime.datetime.now(datetime.timezone.utc)
deals = mt5.history_deals_get(now - datetime.timedelta(hours=6), now)
print("\n--- RECENT CLOSED DEALS (Last 6 Hours) ---")
total_loss = 0
for d in (deals or []):
    if d.profit < 0:
        total_loss += d.profit
    if d.profit != 0:
        print(f"{d.symbol} | Profit: ${d.profit:.2f} | Vol: {d.volume} | Type: {d.type} | Comment: {d.comment}")

print(f"\nTotal Realized Loss (6hr): ${total_loss:.2f}")
