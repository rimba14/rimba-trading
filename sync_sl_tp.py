import MetaTrader5 as mt5
import json
import os

if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

thesis_file = "C:\\Sentinel_Project\\\position_thesis.json"
with open(thesis_file, 'r') as f:
    thesis = json.load(f)

# Tickets identified: 1056526830 (USDJPY), 1056526854 (USDCAD)
targets = ["1056526830", "1056526854"]

for ticket_str in targets:
    if ticket_str in thesis:
        data = thesis[ticket_str]
        ticket = int(ticket_str)
        sl = round(data['sl_barrier'], 5 if "JPY" not in ticket_str else 3)
        tp = round(data['tp_barrier'], 5 if "JPY" not in ticket_str else 3)
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp
        }
        
        print(f"[FIX] Synchronizing Ticket {ticket} Broker-SL to {sl}...")
        
        # Get symbol from MT5 for the ticket
        p_info = mt5.positions_get(ticket=ticket)
        if p_info:
            from gitagent_action_layer import get_action_layer
            result = get_action_layer().modify_position_sltp(p_info[0].symbol, ticket, sl, tp)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[SUCCESS] Ticket {ticket} Updated.")
            else:
                print(f"[FAIL] Ticket {ticket} Update Rejected: {result.comment if result else 'Unknown'}")
        else:
            print(f"[FAIL] Ticket {ticket} not found on server.")


mt5.shutdown()
