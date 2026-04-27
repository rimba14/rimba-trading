import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import time
import os

# =============================================================================
# US OPEN SCALE-OUT EXECUTOR
# Secures 50% profit on VISA/JPM/META at 13:30 UTC
# =============================================================================

SYMBOLS = ['VISA', 'JPM', 'META', 'V']
TARGET_TIME_UTC = "13:30"
LOG_FILE = "C:\\Sentinel_Project\\us_open_log.txt"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    print(msg)

def attempt_scale_out():
    if not mt5.initialize():
        log("MT5 Initialization failed.")
        return False
        
    positions = mt5.positions_get()
    if positions is None:
        log("Error getting positions.")
        mt5.shutdown()
        return False
        
    targets = [p for p in positions if p.symbol in SYMBOLS]
    if not targets:
        log("No target US positions (VISA/JPM/META) found.")
        mt5.shutdown()
        return True # Exit loop, nothing to do
        
    all_success = True
    for pos in targets:
        # Scale out 50%
        sym_info = mt5.symbol_info(pos.symbol)
        if sym_info is None: continue
        
        v_step = sym_info.volume_step
        close_vol_raw = pos.volume * 0.5
        close_vol = round(round(close_vol_raw / v_step) * v_step, 2)
        
        if close_vol < sym_info.volume_min: 
            log(f"Skipping {pos.symbol}, volume too small ({close_vol} < min {sym_info.volume_min})")
            continue
            
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            log(f"Could not get tick for {pos.symbol}")
            all_success = False
            continue
            
        price = tick.bid if pos.type == 0 else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(close_vol),
            "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": 100,
            "comment": "Phase 3 US Scale Out",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        from gitagent_action_layer import get_action_layer
        res = get_action_layer().execute_smart_trade(pos.symbol, mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY, float(close_vol), comment="Phase 3 US Scale Out", position_ticket=pos.ticket)
        
        if res and (res.retcode == 10009 or res.retcode == 10011): # DONE or REQUEST_PLACED
            log(f"SUCCESS: Scaled out {close_vol} lots of {pos.symbol} (Ticket: {pos.ticket})")
        elif res and res.retcode == 10018: # CASE_MARKET_CLOSED
            log(f"REJECTED: {pos.symbol} Market Closed. Retrying later...")
            all_success = False
        else:
            log(f"FAILED: {pos.symbol} Error {res.retcode if res else 'None'} | {res.comment if res else 'Unknown'}")
            all_success = False

            
    mt5.shutdown()
    return all_success

if __name__ == "__main__":
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    log("US Open Executor Started. Monitoring for 13:30 UTC...")
    
    execution_started = False
    
    while True:
        now_utc = datetime.now(timezone.utc)
        current_time = now_utc.strftime("%H:%M")
        
        if current_time >= TARGET_TIME_UTC:
            if not execution_started:
                log(f"Target time {TARGET_TIME_UTC} UTC reached. Initiating scale-out...")
                execution_started = True
                
            if attempt_scale_out():
                log("All US positions scaled successfully or none left. Task Complete.")
                break
            else:
                log("Some positions remain or market is still closed. Retrying in 15s...")
                time.sleep(15)
        else:
            # Sleep more while waiting
            time.sleep(30)
