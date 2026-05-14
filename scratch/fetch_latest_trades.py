import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_last_trades():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    # Look back 1 hour
    from_date = datetime.now() - timedelta(hours=1)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if deals is None or len(deals) == 0:
        print("No trades found in the last hour")
    else:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        print(df[['time', 'symbol', 'type', 'entry', 'price', 'profit', 'volume', 'comment', 'ticket']].tail(10).to_string())

    mt5.shutdown()

if __name__ == "__main__":
    get_last_trades()
