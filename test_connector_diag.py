import MetaTrader5 as mt5
import time
import sys

def run_diagnostic():
    print("=== MT5 Core Diagnostic Sweep (Phase 1) ===")
    
    # 1. API Connection Check
    if not mt5.initialize():
        print("[CRITICAL ERROR] MT5 Initialize failed.")
        return False
    
    # 2. Account Check
    acc = mt5.account_info()
    if acc is None:
        print("[CRITICAL ERROR] Failed to retrieve account info. Terminal might be disconnected.")
        return False
    
    print(f"[OK] Connected to Account: {acc.login} ({acc.company})")
    print(f"[OK] Balance: {acc.balance} {acc.currency} | Equity: {acc.equity} | Leverage: {acc.leverage}")

    # 3. Latency Check
    start_time = time.time()
    for _ in range(5):
        mt5.symbol_info("EURUSD")
    avg_latency = (time.time() - start_time) / 5 * 1000
    print(f"[OK] Average API Latency: {avg_latency:.2f}ms")
    
    if avg_latency > 500:
         print("[WARNING] High latency detected (> 500ms). Performance may be degraded.")

    # 4. Execution Capability Check
    tick = mt5.symbol_info_tick("EURUSD")
    if tick is None:
        print("[CRITICAL ERROR] Cannot receive trade signals (tick data missing).")
        return False
    print(f"[OK] Trade signals (ticks) received. Last EURUSD Bid: {tick.bid}")

    # 5. Trading Allowed Check
    if not acc.trade_allowed:
        print("[CRITICAL ERROR] Auto-trading is disabled in MT5 terminal.")
        return False
    print("[OK] Expert Advisor trading is ENABLED.")

    print("=== Diagnostic Complete: ALL SYSTEMS NOMINAL ===")
    return True

if __name__ == "__main__":
    success = run_diagnostic()
    if not success:
        print("[HALT] Security protocol triggered. Execution halted.")
        sys.exit(1)
    else:
        sys.exit(0)
