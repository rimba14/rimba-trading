import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def main():
    if not mt5.initialize():
        print("MT5 Init Failed")
        return

    tickets = [1303399663, 1303385273]
    found_any = False

    for ticket in tickets:
        deals = mt5.history_deals_get(position=ticket)
        if deals:
            df = pd.DataFrame([d._asdict() for d in deals])
            print(f"\n--- History for Position/Ticket {ticket} ---")
            # Select relevant columns
            cols = ['time', 'symbol', 'type', 'entry', 'volume', 'price', 'profit', 'comment', 'reason', 'magic']
            available_cols = [c for c in cols if c in df.columns]
            print(df[available_cols])
            found_any = True

    if not found_any:
        print("\nTarget tickets not found. Fetching most recent losing trade...")
        now = datetime.now()
        history = mt5.history_deals_get(now - timedelta(days=7), now)
        if history:
            df = pd.DataFrame([d._asdict() for d in history])
            if not df.empty:
                # Filter for closed trades with negative profit
                losing_trades = df[df['profit'] < 0].sort_values(by='time', ascending=False)
                if not losing_trades.empty:
                    target = losing_trades.iloc[0]
                    print(f"\n--- Recent Loser Targeted ---")
                    print(target)
                else:
                    print("No losing trades found in the last 7 days.")
            else:
                print("No history found.")
        else:
            print("Failed to fetch history.")

    mt5.shutdown()

if __name__ == "__main__":
    main()
