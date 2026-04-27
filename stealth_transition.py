import MetaTrader5 as mt5

def transition_to_stealth():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    positions = mt5.positions_get()
    if not positions:
        print("No active positions found.")
        return

    print(f"--- TRANSITIONING {len(positions)} TRADES TO STEALTH ---")
    for p in positions:
        from gitagent_action_layer import get_action_layer
        result = get_action_layer().modify_position_sltp(p.symbol, p.ticket, 0.0, 0.0)

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f" [SUCCESS] Ticket {p.ticket} ({p.symbol}) transitioned to Zero-Token Stealth.")
        else:
            err = mt5.last_error()
            print(f" [FAILED] Ticket {p.ticket} ({p.symbol}) | Error: {result.comment if result else 'Unknown'} | Raw: {err}")

    mt5.shutdown()

if __name__ == "__main__":
    transition_to_stealth()
