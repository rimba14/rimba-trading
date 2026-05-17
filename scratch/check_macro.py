import sys
sys.path.append(r"C:\Sentinel_Project")
from agents.risk_agent import check_upcoming_tier1_events

def main():
    print("==================================================")
    print(" [MACRO AUDIT] TESTING EX-ANTE CALENDAR BLACKOUTS")
    print("==================================================")
    
    symbols = ["EURUSD", "EURPLN", "ETHUSD", "ADAUSD", "SOLUSD"]
    
    for symbol in symbols:
        has_event, desc = check_upcoming_tier1_events(symbol, threshold_hours=24.0)
        status = "BLACKOUT" if has_event else "CLEAR"
        print(f" Symbol: {symbol:<8} | Status: {status:<8} | Description: {desc}")
        
    print("==================================================")

if __name__ == "__main__":
    main()
