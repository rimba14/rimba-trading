import json
import os
import datetime

history_path = "C:/Sentinel_Project/data/p_score_history.jsonl"
if os.path.exists(history_path):
    print("Reading p_score_history.jsonl for target interval...")
    t_start = datetime.datetime(2026, 5, 18, 15, 20, 0).timestamp()
    t_end = datetime.datetime(2026, 5, 18, 15, 35, 0).timestamp()
    
    with open(history_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            try:
                data = json.loads(line)
                ts = data.get('timestamp', 0)
                if t_start <= ts <= t_end:
                    time_str = str(datetime.datetime.fromtimestamp(ts))
                    print(f"Line {line_num} | Time: {time_str} | Data: {data}")
            except Exception:
                pass
else:
    print("p_score_history.jsonl not found.")
