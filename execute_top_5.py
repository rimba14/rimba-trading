import MetaTrader5 as mt5

def execute_top_5():
    trades = [
        ("BTCUSD", "BUY"),
        ("UNIUSD", "BUY"),
        ("NAS100", "BUY"),
        ("ADAUSD", "BUY"),
        ("EURJPY", "BUY")
    ]
    
    if not mt5.initialize():
        print("MT5 initialization failed.")
        return

    print("Pushing top 5 trades to MT5...")
    for sym, side in trades:
        info = mt5.symbol_info(sym)
        if not info:
            print(f"[{sym}] Not found.")
            continue
            
        mt5.symbol_select(sym, True)
        
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            print(f"[{sym}] Failed to get tick data.")
            continue
            
        price = tick.ask if side == "BUY" else tick.bid
        vol = info.volume_min
        
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": vol,
            "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "magic": 142, # Sentinel MAGIC_NUMBER
            "comment": "MANUAL_OVERRIDE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[OK] {sym} {side} @ {price:.5f} (Vol: {vol}) - Ticket: {res.order}")
        else:
            comment = res.comment if res else "Unknown Error"
            print(f"[FAIL] {sym} {side} - Error: {comment}")

    mt5.shutdown()

if __name__ == "__main__":
    execute_top_5()
