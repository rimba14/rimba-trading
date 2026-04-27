import MetaTrader5 as mt5
import json
import os

if not mt5.initialize():
    print("MT5 Init Failed"); quit()

THESIS_FILE = "C:\\Sentinel_Project\\\position_thesis.json"
if not os.path.exists(THESIS_FILE):
    print("No thesis file found"); quit()

with open(THESIS_FILE, 'r') as f:
    thesis = json.load(f)

positions = mt5.positions_get()
if not positions:
    print("No open positions."); quit()

print(f"{'TICKET':<12} | {'SYMBOL':<10} | {'LOCAL_SL':<10} | {'SERVER_SL':<10} | {'STATUS'}")
print("-" * 65)

for p in positions:
    t_id = str(p.ticket)
    if t_id in thesis:
        local_sl = float(thesis[t_id].get('sl_barrier', 0.0))
        local_tp = float(thesis[t_id].get('tp_barrier', 0.0))
        
        # Only modify if broker SL/TP is 0 or significantly different from local
        if (p.sl == 0 and local_sl != 0) or (p.tp == 0 and local_tp != 0) or abs(p.sl - local_sl) > 0.00001:
            print(f"{p.ticket:<12} | {p.symbol:<10} | {local_sl:<10.5f} | {p.sl:<10.5f} | SYNCING...", end="")
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": p.symbol,
                "position": p.ticket,
                "sl": local_sl,
                "tp": local_tp,
                "magic": 123456
            }
            from gitagent_action_layer import get_action_layer
            result = get_action_layer().modify_position_sltp(p.symbol, p.ticket, local_sl, local_tp)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(" DONE")
            else:
                msg = result.comment if result else "Failed"
                print(f" ERROR: {msg}")

        else:
            print(f"{p.ticket:<12} | {p.symbol:<10} | {local_sl:<10.5f} | {p.sl:<10.5f} | OK")

mt5.shutdown()
