import MetaTrader5 as mt5
import sys

def main():
    print("==================================================")
    print(" [MT5 DIAGNOSTIC] AUDITING MT5 TERMINAL STATE")
    print("==================================================")
    
    if not mt5.initialize():
        print(f" [FAIL] mt5.initialize() failed: {mt5.last_error()}")
        sys.exit(1)
        
    print(" [OK] mt5.initialize() passed.")
    
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        print(" [FAIL] mt5.terminal_info() returned None.")
        sys.exit(1)
        
    print("\n--- TERMINAL INFO ---")
    print(f" Connected      : {terminal_info.connected}")
    print(f" Build          : {terminal_info.build}")
    print(f" Company        : {terminal_info.company}")
    print(f" Trade Allowed  : {terminal_info.trade_allowed}")
    
    account_info = mt5.account_info()
    if account_info is not None:
        print("\n--- ACCOUNT INFO ---")
        print(f" Login          : {account_info.login}")
        print(f" Server         : {account_info.server}")
        print(f" Balance        : {account_info.balance:.2f} {account_info.currency}")
        print(f" Equity         : {account_info.equity:.2f} {account_info.currency}")
        print(f" Leverage       : 1:{account_info.leverage}")
        print(f" Trade Mode     : {account_info.trade_mode} (Demo={mt5.ACCOUNT_TRADE_MODE_DEMO}, Real={mt5.ACCOUNT_TRADE_MODE_REAL})")
        if "DEMO" in account_info.server.upper() or account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO:
            print(" [WARNING] Connected to DEMO Account!")
        else:
            print(" [PASS] Connected to LIVE Broker Server!")
    else:
        print("\n--- ACCOUNT INFO ---")
        print(" [WARN] Account info not available (possibly not logged in).")
        
    # Get spread for EURUSD and EURPLN
    for symbol in ["EURUSD", "EURPLN"]:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is not None:
            print(f"\n--- {symbol} TICK INFO ---")
            print(f"  Spread (points) : {symbol_info.spread}")
            print(f"  Ask             : {symbol_info.ask}")
            print(f"  Bid             : {symbol_info.bid}")
            print(f"  Point           : {symbol_info.point}")
            # Calculate actual spread in price points
            actual_spread = symbol_info.spread * symbol_info.point
            print(f"  Spread (price)  : {actual_spread:.5f}")
            safety_floor = 1.5 * actual_spread
            print(f"  Spread-Aware Floor (1.5x): {safety_floor:.5f}")
        else:
            print(f"\n--- {symbol} ---")
            print(f"  [FAIL] Failed to retrieve symbol info.")
            
    mt5.shutdown()
    print("\n==================================================")

if __name__ == "__main__":
    main()
