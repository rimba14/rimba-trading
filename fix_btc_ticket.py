import MetaTrader5 as mt5
import sys

def sweep_all_naked():
    if not mt5.initialize():
        print("[ERROR] MT5 init failed.")
        return

    positions = mt5.positions_get() or []
    naked_pos = [p for p in positions if p.tp == 0.0 or p.sl == 0.0]

    if not naked_pos:
        print("[SUCCESS] Live environment verification passed: Absolutely zero naked positions found.")
        mt5.shutdown()
        return

    print(f"[SWEEP] Sweeping {len(naked_pos)} naked positions...")
    for pos in naked_pos:
        info = mt5.symbol_info(pos.symbol)
        if not info:
            print(f"[ERROR] Symbol info not found for {pos.symbol}.")
            continue

        raw_atr = 0.0010
        price_based_min = pos.price_open * 0.0025
        broker_min = info.trade_stops_level * info.point
        true_atr = max(raw_atr, price_based_min, broker_min)

        tp_dist = 3.0 * true_atr
        sl_dist = 1.2 * true_atr

        if pos.type == mt5.ORDER_TYPE_BUY:
            new_tp = pos.price_open + tp_dist
            new_sl = pos.price_open - sl_dist
        elif pos.type == mt5.ORDER_TYPE_SELL:
            new_tp = pos.price_open - tp_dist
            new_sl = pos.price_open + sl_dist
        else:
            continue

        final_tp = pos.tp if pos.tp > 0.0 else new_tp
        final_sl = pos.sl if pos.sl > 0.0 else new_sl

        tick_size = info.trade_tick_size
        if tick_size > 0:
            final_tp = round(final_tp / tick_size) * tick_size
            if final_sl > 0:
                final_sl = round(final_sl / tick_size) * tick_size

        final_tp = round(final_tp, info.digits)
        final_sl = round(final_sl, info.digits) if final_sl > 0 else 0.0

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": final_sl,
            "tp": final_tp
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[SWEEP SUCCESS] Ticket #{pos.ticket} ({pos.symbol}) modified: SL={final_sl} | TP={final_tp}")
        else:
            err = mt5.last_error()
            print(f"[SWEEP REJECTION] Ticket #{pos.ticket} failed. Retcode: {result.retcode if result else 'None'} | MT5 Error: {err}")

    # Verify final compliance
    remaining = mt5.positions_get() or []
    still_naked = [p.ticket for p in remaining if p.tp == 0.0 or p.sl == 0.0]
    if not still_naked:
        print("[SUCCESS] Pipeline fully compliant. Zero naked positions remain active.")
    else:
        print(f"[WARNING] Some positions still naked after sweep attempt: {still_naked}")

    mt5.shutdown()

if __name__ == "__main__":
    sweep_all_naked()
