import MetaTrader5 as mt5
import logging
import sys

def broker_audit():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    symbols = ["BTCUSD", "US2000", "EURUSD", "XAUUSD"]
    print("--- Symbol Trade Mode Audit ---")
    
    trade_mode_map = {
        0: "DISABLED",
        1: "LONG_ONLY",
        2: "SHORT_ONLY",
        3: "CLOSE_ONLY",
        4: "FULL"
    }

    for sym in symbols:
        info = mt5.symbol_info(sym)
        if info is None:
            # Try to select it first
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            
        if info:
            mode = info.trade_mode
            mode_str = trade_mode_map.get(mode, f"UNKNOWN({mode})")
            print(f"{sym}: Trade Mode = {mode} ({mode_str})")
        else:
            print(f"{sym}: SYMBOL NOT FOUND")

    print("\n--- order_check Dry-Run: BTCUSD ---")
    symbol = "BTCUSD"
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    
    if info and tick:
        # Construct mock order
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": info.volume_min,
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "magic": 123456,
            "comment": "PREFLIGHT_CHECK",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        check_result = mt5.order_check(request)
        if check_result is None:
            print(f"order_check returned None. MT5 Error: {mt5.last_error()}")
        else:
            print(f"Retcode: {check_result.retcode}")
            print(f"Comment: {check_result.comment}")
            print(f"Margin Free After Trade: {check_result.margin_free}")
            if check_result.retcode != 0:
                # Some brokers return 0 for check success, others return 10008 or 10009
                # Actually, according to MT5 docs, order_check returns a MqlTradeCheckResult
                # where retcode 0 means success in some contexts, but usually retcode is check outcome.
                pass
    else:
        print(f"Could not perform check for {symbol}: Info or Tick missing.")

    mt5.shutdown()

if __name__ == "__main__":
    broker_audit()
