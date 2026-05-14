import re

def analyze_log_scores():
    log_path = r"C:\sentinel_logs\fastapi_sniper_v2.log"
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log: {e}")
        return
        
    btc_signals = []
    for line in lines:
        if "Received Signal: BTCUSD" in line:
            btc_signals.append(line.strip())
            
    print(f"Total BTC signals found in log: {len(btc_signals)}")
    for s in btc_signals[-25:]:
        print(s)

if __name__ == "__main__":
    analyze_log_scores()
