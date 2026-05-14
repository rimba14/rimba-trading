import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_xauusd_deals():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    # Look back 1 week
    from_date = datetime.now() - timedelta(days=7)
    deals = mt5.history_deals_get(from_date, datetime.now(), group="*XAUUSD*")
    
    if deals is None:
        print("No XAUUSD deals found")
    else:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        print(df[['time', 'symbol', 'type', 'entry', 'price', 'profit', 'volume', 'comment']].to_string())

    mt5.shutdown()

if __name__ == "__main__":
    get_xauusd_deals()
