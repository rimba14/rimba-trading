import MetaTrader5 as mt5
import sys

def close_position(ticket):
    if not mt5.initialize():
        print("FAIL")
        return
    
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        print(f"Ticket {ticket} not found")
        return
    
    p = pos[0]
    symbol = p.symbol
    volume = p.volume
    type_close = mt5.ORDER_TYPE_BUY if p.type == 1 else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(symbol).ask if type_close == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": type_close,
        "position": ticket,
        "price": price,
        "magic": p.magic,
        "comment": "CLEANUP_v17.3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    res = mt5.order_send(request)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"SUCCESS: {ticket} closed")
    else:
        print(f"FAIL: {res.comment}")
    
    mt5.shutdown()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        close_position(int(sys.argv[1]))
