import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NAS_FORENSICS")

def do_forensics():
    if not mt5.initialize():
        logger.error("MT5 init failed")
        return

    # Get deals from the last 7 days
    to_date = datetime.now()
    from_date = to_date - timedelta(days=30)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        logger.error("No deals found in history.")
        mt5.shutdown()
        return
        
    df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter for NAS100
    df_nas = df_deals[df_deals['symbol'].str.contains("NAS100", case=False, na=False)].copy()
    
    if df_nas.empty:
        logger.error("No NAS100 deals found in the last 30 days.")
        mt5.shutdown()
        return

    # A trade that hits a Stop Loss usually has a comment containing 'sl' or is closed at a loss
    # We will look for closed positions (deal type DEAL_TYPE_BUY or DEAL_TYPE_SELL with entry == DEAL_ENTRY_OUT)
    # Actually, we can just look at deals where entry == 1 (DEAL_ENTRY_OUT) and profit < 0
    df_exits = df_nas[(df_nas['entry'] == 1)].copy()
    df_losses = df_exits[df_exits['profit'] < 0].copy()
    
    df_losses = df_losses.sort_values(by='time', ascending=False)
    
    logger.info("=================================================================")
    logger.info("               NAS100 FORENSICS - LAST 2 STOP LOSSES             ")
    logger.info("=================================================================")
    
    if len(df_losses) < 2:
        logger.warning(f"Found only {len(df_losses)} losing NAS100 exits. Showing all.")
        top_2_losses = df_losses
    else:
        top_2_losses = df_losses.head(2)
        
    for _, row in top_2_losses.iterrows():
        pos_id = row['position_id']
        exit_time = pd.to_datetime(row['time'], unit='s')
        exit_price = row['price']
        profit = row['profit']
        comment = row['comment']
        
        # Find the entry deal for this position
        entry_deals = df_nas[(df_nas['position_id'] == pos_id) & (df_nas['entry'] == 0)]
        if not entry_deals.empty:
            entry_row = entry_deals.iloc[-1]
            entry_time = pd.to_datetime(entry_row['time'], unit='s')
            entry_price = entry_row['price']
            direction = "BUY" if entry_row['type'] == mt5.DEAL_TYPE_BUY else "SELL"
            logger.info(f"Position: {pos_id} | {direction}")
            logger.info(f"Entry: {entry_time} @ {entry_price}")
            logger.info(f"Exit : {exit_time} @ {exit_price}")
            logger.info(f"Loss : {profit} | Comment: {comment}")
            
            # Fetch M15 data around this time to see structural context
            start_time = entry_row['time'] - 3600*2 # 2 hours before entry
            end_time = row['time'] + 3600*2 # 2 hours after exit
            rates = mt5.copy_rates_range("NAS100", mt5.TIMEFRAME_M15, start_time, end_time)
            if rates is not None and len(rates) > 0:
                df_rates = pd.DataFrame(rates)
                max_high = df_rates['high'].max()
                min_low = df_rates['low'].min()
                logger.info(f"Market Context (M15): Local High={max_high}, Local Low={min_low}")
        else:
            logger.info(f"Position {pos_id} missing entry data. Exit time: {exit_time}, Profit: {profit}")
            
        logger.info("-----------------------------------------------------------------")
        
    mt5.shutdown()

if __name__ == "__main__":
    do_forensics()
