import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def analyze_btc_trades():
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    from_date = datetime.now() - timedelta(hours=24)
    to_date = datetime.now()
    
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None or len(deals) == 0:
        print("No deals found in history.")
        mt5.shutdown()
        return

    # Convert to DataFrame
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Filter for BTC symbols
    btc_df = df[df['symbol'].str.contains("BTC", na=False)].copy()
    if btc_df.empty:
        print("No BTC deals found in history.")
        mt5.shutdown()
        return

    btc_df = btc_df.sort_values('time').reset_index(drop=True)
    print("=== All BTC Deals over last 24h ===")
    print("Columns available:", btc_df.columns.tolist())
    cols = [c for c in ['time', 'symbol', 'ticket', 'order', 'type', 'entry', 'price', 'volume', 'profit', 'comment', 'position_id'] if c in btc_df.columns]
    print(btc_df[cols].to_string())
    
    mt5.shutdown()

if __name__ == "__main__":
    analyze_btc_trades()
