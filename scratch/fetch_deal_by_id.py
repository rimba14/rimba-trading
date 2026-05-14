import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def get_specific_deal(deal_id):
    if not mt5.initialize():
        print("MT5 Initialization failed")
        return

    # history_deals_get by ticket doesn't exist, we use position_id
    # But we can look at history_deals_get and filter
    from_date = datetime.now() - timedelta(days=60) # Look back far
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if deals:
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        target = df[df['position_id'] == deal_id]
        if target.empty:
            target = df[df['ticket'] == deal_id]
        
        if not target.empty:
            print(target.to_string())
        else:
            print(f"Deal {deal_id} not found in history")

    mt5.shutdown()

if __name__ == "__main__":
    get_specific_deal(1146452856)
