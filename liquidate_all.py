import MetaTrader5 as mt5
import time

def liquidate_all():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    positions = mt5.positions_get()
    if not positions:
        print("No active positions found.")
    else:
        print(f"Found {len(positions)} positions. Closing all...")
        for p in positions:
            symbol = p.symbol
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
                "comment": "MASS_LIQUIDATION",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to close {p.ticket} ({symbol}): {res.comment}")
            else:
                print(f"Closed {p.ticket} ({symbol}) successfully.")
            time.sleep(0.1)

    # Also cancel pending orders
    orders = mt5.orders_get()
    if orders:
        print(f"Found {len(orders)} pending orders. Cancelling all...")
        for o in orders:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": o.ticket
            }
            res = mt5.order_send(request)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"Failed to cancel order {o.ticket}: {res.comment}")
            else:
                print(f"Cancelled order {o.ticket} successfully.")

    print("Liquidation Complete.")
    mt5.shutdown()

if __name__ == "__main__":
    liquidate_all()
