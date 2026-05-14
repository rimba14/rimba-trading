import sys
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import traceback

sys.path.append(r"C:\Sentinel_Project")

def is_amnesia_lock_active(symbol, cooldown_seconds=300):
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"  [AMNESIA] symbol_info({symbol}) returned None. MT5 Error: {mt5.last_error()}")
        return False
    current_broker_time = info.time
    print(f"  [AMNESIA] Current broker time for {symbol}: {current_broker_time} ({datetime.fromtimestamp(current_broker_time)})")

    now = datetime.now()
    yesterday = now - timedelta(days=1)
    tomorrow  = now + timedelta(days=1)

    deals = mt5.history_deals_get(yesterday, tomorrow, group=f"*{symbol}*")
    if deals is None or len(deals) == 0:
        print(f"  [AMNESIA] No recent deals for {symbol}. LOCK = False (CLEAR TO TRADE).")
        return False

    last_deal_time = max([deal.time for deal in deals])
    time_since = current_broker_time - last_deal_time
    locked = 0 <= time_since < cooldown_seconds
    print(f"  [AMNESIA] Last deal: {datetime.fromtimestamp(last_deal_time)} | Delta: {time_since}s | LOCK = {locked}")
    return locked

if __name__ == "__main__":
    print("=== Amnesia Lock Isolation Test ===\n")
    if not mt5.initialize():
        print(f"FATAL: MT5 Init failed: {mt5.last_error()}")
        sys.exit(1)

    for sym in ["ETHUSD", "CADJPY", "AUDCHF", "XAUUSD"]:
        print(f"\n[TEST] {sym}")
        try:
            result = is_amnesia_lock_active(sym)
            print(f"  => is_amnesia_lock_active('{sym}') = {result}")
        except Exception:
            print(f"  => EXCEPTION:\n{traceback.format_exc()}")

    mt5.shutdown()
    print("\n=== Test Complete ===")
