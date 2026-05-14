def find_whipsaw_scores():
    log_path = r"C:\sentinel_logs\slow_loop_v17_9.log"
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error: {e}")
        return
        
    targets = ["09:02:1", "09:32:2", "10:22:0", "17:33:3"]
    for i, line in enumerate(lines):
        if any(t in line for t in targets) and "BTCUSD" in line:
            # print surrounding lines
            start = max(0, i-8)
            end = min(len(lines), i+3)
            print(f"\n--- Context around {line.strip()[:20]} ---")
            for j in range(start, end):
                print(lines[j].strip())

if __name__ == "__main__":
    find_whipsaw_scores()
