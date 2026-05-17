import MetaTrader5 as mt5
from datetime import datetime, timezone
import sys

def main():
    print("==================================================")
    print(" [BROKER TIME DIAGNOSTIC] AUDITING ROLLOVER WINDOW")
    print("==================================================")
    
    if not mt5.initialize():
        print(" [FAIL] mt5.initialize() failed.")
        sys.exit(1)
        
    tick = mt5.symbol_info_tick("EURUSD")
    if tick is None:
        print(" [FAIL] Failed to retrieve EURUSD tick for broker time.")
        mt5.shutdown()
        sys.exit(1)
        
    broker_dt = datetime.fromtimestamp(tick.time, timezone.utc)
    print(f" Current Broker UTC Time : {broker_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Hour                     : {broker_dt.hour}")
    print(f" Minute                   : {broker_dt.minute}")
    
    # Rollover check
    is_rollover = (broker_dt.hour == 23 and broker_dt.minute >= 55) or (broker_dt.hour == 0 and broker_dt.minute <= 15)
    
    if is_rollover:
        print(" [BLACKOUT] Currently INSIDE the Rollover Blackout Window (23:55 - 00:15)!")
    else:
        print(" [CLEAR] Currently OUTSIDE the Rollover Blackout Window. Gating clear.")
        
    mt5.shutdown()
    print("==================================================")

if __name__ == "__main__":
    main()
