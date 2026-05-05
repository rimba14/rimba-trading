import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta

def analyze_slippage_latency():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    now = datetime.now(timezone.utc)
    orders = mt5.history_orders_get(now - timedelta(days=30), now)
    
    latencies = []
    slippages_pips = []
    
    if orders:
        for o in orders:
            if o.magic in [142, 17300] and o.state == mt5.ORDER_STATE_FILLED:
                # Execution latency in milliseconds
                lat_ms = o.time_done_msc - o.time_setup_msc
                latencies.append(lat_ms)
                
                # Slippage in points
                deals = mt5.history_deals_get(ticket=o.ticket)
                # Wait, order.ticket might not be the same as deal.ticket, it's deal.order
                deals = mt5.history_deals_get(now - timedelta(days=30), now)
                
                # To be faster, let's just use the known order and deal mapping
                # MT5 order has price_open, and price_current
                # Slippage = difference between expected price and actual fill price
                # For Market orders, price_open is often 0 or the current tick when requested
                # Let's see if we can use the order's price vs deal's price
                pass

    deals = mt5.history_deals_get(now - timedelta(days=30), now)
    if deals and orders:
        order_dict = {o.ticket: o for o in orders if o.state == mt5.ORDER_STATE_FILLED}
        for d in deals:
            if d.order in order_dict:
                o = order_dict[d.order]
                # If market order, o.price_open might be requested price
                if o.price_open > 0:
                    diff = abs(o.price_open - d.price)
                    symbol_info = mt5.symbol_info(d.symbol)
                    if symbol_info:
                        point = symbol_info.point
                        if point > 0:
                            slip_pips = diff / point
                            slippages_pips.append(slip_pips)

    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    avg_slip = sum(slippages_pips) / len(slippages_pips) if slippages_pips else 0
    
    print(f"Average Execution Latency: {avg_lat:.0f} ms")
    print(f"Average Slippage: {avg_slip:.2f} points/pips")

    mt5.shutdown()

if __name__ == "__main__":
    analyze_slippage_latency()
