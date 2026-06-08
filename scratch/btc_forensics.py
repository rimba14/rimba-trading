import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BTC_FORENSICS")

def do_forensics():
    if not mt5.initialize():
        logger.error("MT5 init failed")
        return

    # Get deals from the last 7 days
    to_date = datetime.now()
    from_date = to_date - timedelta(days=7)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals:
        logger.error("No deals found in history.")
        mt5.shutdown()
        return
        
    df_deals = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    
    # Filter for BTCUSD
    df_btc = df_deals[df_deals['symbol'].str.contains("BTCUSD", case=False, na=False)].copy()
    
    if df_btc.empty:
        logger.error("No BTCUSD deals found in the last 7 days.")
        mt5.shutdown()
        return

    df_exits = df_btc[(df_btc['entry'] == 1)].copy()
    df_losses = df_exits[df_exits['profit'] <= 0].copy() # includes flat closes if stopped out by system
    
    df_losses = df_losses.sort_values(by='time', ascending=False)
    
    logger.info("=================================================================")
    logger.info("               BTCUSD FORENSICS - LATEST EXIT                    ")
    logger.info("=================================================================")
    
    if len(df_losses) < 1:
        logger.warning(f"No losing/flat BTCUSD exits found.")
        mt5.shutdown()
        return
        
    latest_loss = df_losses.iloc[0]
        
    pos_id = latest_loss['position_id']
    exit_time = pd.to_datetime(latest_loss['time'], unit='s')
    exit_price = latest_loss['price']
    profit = latest_loss['profit']
    comment = latest_loss['comment']
    
    entry_deals = df_btc[(df_btc['position_id'] == pos_id) & (df_btc['entry'] == 0)]
    if not entry_deals.empty:
        entry_row = entry_deals.iloc[-1]
        entry_time = pd.to_datetime(entry_row['time'], unit='s')
        entry_price = entry_row['price']
        direction = "BUY" if entry_row['type'] == mt5.DEAL_TYPE_BUY else "SELL"
        logger.info(f"Position: {pos_id} | {direction}")
        logger.info(f"Entry: {entry_time} @ {entry_price}")
        logger.info(f"Exit : {exit_time} @ {exit_price}")
        logger.info(f"P&L  : {profit} | Comment: {comment}")
        
        # Fetch M15 data around this time to see structural context
        start_time = entry_row['time'] - 3600*2 
        end_time = latest_loss['time'] + 3600*2 
        rates = mt5.copy_rates_range("BTCUSD", mt5.TIMEFRAME_M15, start_time, end_time)
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
