import MetaTrader5 as mt5
import sys

def run_intervention():
    if not mt5.initialize():
        print("🚨 MT5 init failed.")
        return

    ticket = 1292453710
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        print(f"🚨 Position #{ticket} not found or already closed.")
        mt5.shutdown()
        return

    pos = positions[0]
    info = mt5.symbol_info(pos.symbol)
    if not info:
        print(f"🚨 Symbol info not found for {pos.symbol}.")
        mt5.shutdown()
        return

    # Calculate True ATR using the 0.25% absolute magnitude floor
    true_atr = max(0.0010, pos.price_open * 0.0025, info.trade_stops_level * info.point)
    tp_dist = 3.0 * true_atr

    # Calculate absolute TP price
    if pos.type == mt5.ORDER_TYPE_BUY:
        new_tp = pos.price_open + tp_dist
    elif pos.type == mt5.ORDER_TYPE_SELL:
        new_tp = pos.price_open - tp_dist
    else:
        print(f"🚨 Unsupported position type: {pos.type}")
        mt5.shutdown()
        return

    # Apply Tick Size Normalization
    if info.trade_tick_size > 0:
        new_tp = round(new_tp / info.trade_tick_size) * info.trade_tick_size

    new_tp = round(new_tp, info.digits)

    # Modification Payload preserving current Stop-Loss
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": pos.ticket,
        "sl": pos.sl,
        "tp": new_tp
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[TARGETED INTERVENTION SUCCESS] Ticket #{ticket} successfully modified. New TP is: {new_tp:.2f}")
    else:
        err = mt5.last_error()
        print(f"🚨 Modification failed. Retcode: {result.retcode if result else 'None'} | MT5 Error: {err}")

    mt5.shutdown()

if __name__ == "__main__":
    run_intervention()
