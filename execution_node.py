import numpy as np
import MetaTrader5 as mt5

def almgren_chriss_slicer(total_lots, num_orders):
    """
    Slices a large order into child orders using Almgren-Chriss logic.
    """
    child_size = total_lots / num_orders
    trajectory = [child_size] * num_orders
    return trajectory

def execute_order(symbol, lots, order_type="BUY"):
    if lots >= 10.0: # Threshold for Almgren-Chriss
        print(f"Large Order Detected: {lots} lots on {symbol}. Initiating Almgren-Chriss Slicing...")
        num_slices = 5
        trajectory = almgren_chriss_slicer(lots, num_slices)
        print(f"Child Order Trajectory: {trajectory}")
        for i, slice_size in enumerate(trajectory):
            send_mt5_order(symbol, slice_size, order_type, comment=f"v23.0 AC {i+1}")
    else:
        print(f"Executing block order: {lots} lots on {symbol}")
        send_mt5_order(symbol, lots, order_type, comment="v23.0 Block")

def send_mt5_order(symbol, lots, direction, comment=""):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"Error: Could not get tick info for {symbol}")
        return False
    
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": price,
        "magic": 142,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"MT5 Order Failed: {result.retcode} - {result.comment}")
        return False
    
    print(f"MT5 Order Executed: {symbol} {direction} {lots} lots @ {price}")
    return True

if __name__ == "__main__":
    # Diagnostic test (requires MT5 initialized)
    if mt5.initialize():
        execute_order("XAUUSD", 0.01)
        print("Execution Node diagnostic: SUCCESS")
    else:
        print("MT5 Init failed for diagnostic.")
