import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_xau_history():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    from_date = datetime.now() - timedelta(days=2)
    deals = mt5.history_deals_get(from_date, datetime.now(), group="*XAUUSD*")
    
    if deals:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        # Sort by position_id and then time
        df = df.sort_values(['position_id', 'time'])
        print(df[['time', 'symbol', 'type', 'entry', 'price', 'profit', 'volume', 'comment', 'position_id']].to_string())
    else:
        print("No XAUUSD deals in last 2 days")

    mt5.shutdown()

if __name__ == "__main__":
    get_xau_history()
