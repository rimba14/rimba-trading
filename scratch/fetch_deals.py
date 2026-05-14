import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_last_deals():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    # Look back 3 days
    from_date = datetime.now() - timedelta(days=3)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if deals is None:
        print("No deals found")
    else:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        # Filter for real trades (not funding/etc)
        # Entry/Exit deals
        df = df[df['entry'] != 2] # 2 is for balance/funding usually? Actually check MT5 docs.
        # entry: 0=IN, 1=OUT, 2=IN/OUT (reversal)
        print(df[['time', 'symbol', 'type', 'entry', 'price', 'profit', 'volume', 'comment']].tail(10).to_string())

    mt5.shutdown()

if __name__ == "__main__":
    get_last_deals()
