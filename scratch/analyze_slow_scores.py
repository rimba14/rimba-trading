def analyze_slow_scores():
    log_path = r"C:\sentinel_logs\slow_loop_v17_9.log"
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading log: {e}")
        return
        
    btc_lines = [l.strip() for l in lines if "[BTCUSD]" in l or "BTCUSD ->" in l]
    print(f"Total BTC slow loop entries: {len(btc_lines)}")
    for l in btc_lines[-30:]:
        print(l)

if __name__ == "__main__":
    analyze_slow_scores()
