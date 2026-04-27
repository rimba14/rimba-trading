import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("MT5 Init Failed")
    quit()

# Check today's history
from_date = datetime.now() - timedelta(days=1)
to_date = datetime.now()

deals = mt5.history_deals_get(from_date, to_date)
if deals is None:
    print("No deals found")
else:
    df = pd.DataFrame(list(deals), columns=deals[0]._as_dict().keys())
    # Filter for BCH and XPT
    df_filtered = df[df['symbol'].str.contains('BCH|XPT', case=False, na=False)]
    
    if df_filtered.empty:
        print("No recent deals for BCH or XPT")
    else:
        # Convert timestamps
        df_filtered['time'] = pd.to_datetime(df_filtered['time'], unit='s')
        
        # Select relevant columns
        cols = ['time', 'symbol', 'type', 'entry', 'volume', 'price', 'profit', 'comment', 'magic', 'reason']
        print(df_filtered[cols].to_string())

mt5.shutdown()
