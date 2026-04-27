import MetaTrader5 as mt5
import json
import os

if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

thesis = {}
try:
    with open('C:\\Sentinel_Project\\position_thesis.json', 'r') as f:
        thesis = json.load(f)
except:
    pass

positions = mt5.positions_get()
if not positions:
    print("No open positions found.")
else:
    print(f"{'TICKET':<12} | {'SYMBOL':<10} | {'TYPE':<5} | {'SENTINEL STATUS'}")
    print("-" * 50)
    for p in positions:
        if "EUR" in p.symbol:
            ticket_str = str(p.ticket)
            data = thesis.get(ticket_str, {})
            has_sentinel = "sl_barrier" in data
            status = "ACTIVE" if has_sentinel else "LEGACY (Score Only)" if ticket_str in thesis else "UNMONITORED"
            p_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            print(f"{p.ticket:<12} | {p.symbol:<10} | {p_type:<5} | {status}")

mt5.shutdown()
