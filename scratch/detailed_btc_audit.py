import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def detailed_btc_audit():
    if not mt5.initialize():
        print("MT5 Init failed")
        return
        
    deals = mt5.history_deals_get(datetime.now() - timedelta(hours=24), datetime.now())
    if not deals:
        print("No deals")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    btc_df = df[df['symbol'].str.contains("BTC", na=False)].sort_values('time').reset_index(drop=True)
    
    deal_type_map = {0: "BUY", 1: "SELL"}
    entry_map = {0: "IN (Open)", 1: "OUT (Close)", 2: "INOUT"}
    
    btc_df['type_str'] = btc_df['type'].map(deal_type_map)
    btc_df['entry_str'] = btc_df['entry'].map(entry_map)
    
    cols = ['time', 'ticket', 'type_str', 'entry_str', 'price', 'volume', 'profit', 'comment', 'position_id']
    print(btc_df[cols].tail(15).to_string())
    mt5.shutdown()

if __name__ == "__main__":
    detailed_btc_audit()
