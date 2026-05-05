import MetaTrader5 as mt5
from datetime import datetime, timedelta

def check_history():
    if not mt5.initialize():
        print("FAILED MT5 init")
        return
    
    # Check last 1 hour of deals
    now = datetime.now()
    from_date = now - timedelta(hours=1)
    deals = mt5.history_deals_get(from_date, now)
    
    if deals:
        import pandas as pd
        df = pd.DataFrame([d._asdict() for d in deals])
        print("--- RECENT MT5 DEALS ---")
        print(df[['ticket', 'symbol', 'type', 'profit', 'comment']].to_string(index=False))
    else:
        print("No recent deals in history.")
        
    mt5.shutdown()

if __name__ == "__main__":
    check_history()
