import MetaTrader5 as mt5
import sys
import os

# Ensure project root is in path
sys.path.append(r'C:\Sentinel_Project')

from fastapi_sniper import enforce_stoplevel_and_normalize

def emergency_fix():
    if not mt5.initialize():
        print("MT5 Init failed")
        return

    symbol = 'XRPUSD'
    pos = mt5.positions_get(symbol=symbol)
    if not pos:
        print(f"No open positions for {symbol}")
        return

    for p in pos:
        print(f"Fixing Ticket #{p.ticket} | Current SL: {p.sl} | Open: {p.price_open} | TP: {p.tp}")
        
        info = mt5.symbol_info(symbol)
        if not info:
            print(f"Could not get symbol info for {symbol}")
            continue

        # Calculate a safe SL (1% below current price for Long)
        is_buy = (p.type == mt5.ORDER_TYPE_BUY)
        tick = mt5.symbol_info_tick(symbol)
        curr_price = tick.bid if is_buy else tick.ask
        
        # Use a very safe distance from CURRENT price, not open price
        # because the trade is in loss.
        if is_buy:
            target_sl = curr_price - (200 * info.point) # 200 points below current
        else:
            target_sl = curr_price + (200 * info.point) # 200 points above current

        # Ironclad normalization
        final_sl = enforce_stoplevel_and_normalize(symbol, curr_price, target_sl, is_sl=True, is_buy=is_buy)
        final_tp = p.tp # DO NOT TOUCH TP
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": p.ticket,
            "sl": final_sl,
            "tp": final_tp
        }
        
        print(f"SURGICAL FIX: Ticket #{p.ticket} | Curr Price: {curr_price} | New SL: {final_sl} | Keep TP: {final_tp}")
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"FAILED: {result.retcode} | {result.comment}")
        else:
            print("SUCCESS! Stop-Loss Armored.")

    mt5.shutdown()

if __name__ == "__main__":
    emergency_fix()
