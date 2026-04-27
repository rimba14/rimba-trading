import MetaTrader5 as mt5
import time

def cleanup_eurusd():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    symbol = "EURUSD"
    magic = 120
    
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        print(f"No {symbol} positions found.")
        return

    target_positions = [p for p in positions if p.magic == magic]
    print(f"Found {len(target_positions)} redundant positions for {symbol} with magic {magic}.")

    for p in target_positions:
        print(f"Closing Ticket: {p.ticket}...")
        tick = mt5.symbol_info_tick(symbol)
        order_type = mt5.ORDER_TYPE_BUY if p.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL
        price = tick.ask if p.type == mt5.ORDER_TYPE_SELL else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": p.volume,
            "type": order_type,
            "position": p.ticket,
            "price": price,
            "deviation": 20,
            "magic": 999,
            "comment": "CLEANUP_LOOP_ENTRY",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Failed to close {p.ticket}: {res.comment}")
        else:
            print(f"Closed {p.ticket} successfully.")
        
        time.sleep(0.1) # Avoid rate limit

    print("Cleanup Complete.")
    mt5.shutdown()

if __name__ == "__main__":
    cleanup_eurusd()
