import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def analyze_tickets():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    tickets = [1293954401, 1294194018, 1294185955, 1293817869, 1294212409, 1300315429]
    for t in tickets:
        # Get deals for this ticket
        deals = mt5.history_deals_get(ticket=t)
        if deals:
            for d in deals:
                print(f"--- Deal for Ticket {t} ---")
                print(f"Symbol: {d.symbol}")
                print(f"Type: {'BUY' if d.type == mt5.DEAL_TYPE_BUY else 'SELL'}")
                print(f"Entry/Exit: {'ENTRY' if d.entry == mt5.ENTRY_IN else 'EXIT'}")
                print(f"Price: {d.price}")
                print(f"Profit: {d.profit}")
                print(f"Time: {datetime.fromtimestamp(d.time)}")
                print(f"Comment: {d.comment}")
                print(f"Ticket: {d.ticket}")
                print(f"Order: {d.order}")
        else:
            # Try history_orders_get
            orders = mt5.history_orders_get(ticket=t)
            if orders:
                for o in orders:
                    print(f"--- Order for Ticket {t} ---")
                    print(f"Symbol: {o.symbol}")
                    print(f"Status: {o.state}")
                    print(f"Comment: {o.comment}")
            else:
                print(f"Ticket {t} not found in history.")

    mt5.shutdown()

if __name__ == "__main__":
    analyze_tickets()
