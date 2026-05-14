import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz

def investigate():
    tickets = [1286047526, 1286047548]
    
    print("=== MT5 HISTORY CHECK ===")
    if mt5.initialize():
        # FIX 1: Use timezone-aware UTC datetimes to prevent Broker/Local time desyncs
        utc_tz = pytz.timezone("Etc/UTC")
        to_date = datetime.now(utc_tz) + timedelta(days=1) # Buffer to catch late server ticks
        from_date = to_date - timedelta(days=7)
        
        deals = mt5.history_deals_get(from_date, to_date)
        
        if deals:
            # FIX 2: Safer DataFrame instantiation for MT5 tuples
            df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            for t in tickets:
                res = df[(df['ticket'] == t) | (df['position_id'] == t) | (df['order'] == t)]
                if not res.empty:
                    print(f"\n--- Matches for {t} in Deals ---")
                    cols = [c for c in ['time', 'symbol', 'ticket', 'order', 'type', 'entry', 'price', 'volume', 'profit', 'comment', 'position_id'] if c in df.columns]
                    print(res[cols].to_string())
                else:
                    print(f"No MT5 deals match {t} in the last 7 days.")
        else:
            # FIX 3: Catch and expose silent MT5 API failures
            error = mt5.last_error()
            print(f"Failed to fetch deals. MT5 Error Code: {error}")
            
        mt5.shutdown()
    else:
        print("MT5 Init Failed")
        
    print("\n=== LOGS CHECK ===")
    log_path = r"C:\sentinel_logs\fastapi_sniper_v2.log"
    try:
        matches = {str(t): [] for t in tickets}
        
        # FIX 4: Line-by-line iteration to prevent OOM RAM crashes on massive log files
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                for t in tickets:
                    if str(t) in line:
                        matches[str(t)].append(line.strip())
        
        for t, lines in matches.items():
            print(f"\nLog matches for {t}: {len(lines)}")
            # Print only the last 5 logs for cleaner terminal output
            for m in lines[-5:]:
                print(m)
                
    except FileNotFoundError:
        print(f"Log file not found at: {log_path}")
    except Exception as e:
        print(f"Log read error: {e}")

if __name__ == "__main__":
    investigate()
