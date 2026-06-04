import json
import os
import datetime

history_path = "C:/Sentinel_Project/data/p_score_history.jsonl"
if os.path.exists(history_path):
    print("Reading p_score_history.jsonl...")
    matches = []
    with open(history_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            if "CL-OIL" in line:
                try:
                    data = json.loads(line)
                    matches.append((line_num, data))
                except Exception:
                    pass
    print(f"Found {len(matches)} matches for CL-OIL:")
    for idx, data in matches[-15:]: # print last 15 matches
        ts = data.get('timestamp')
        time_str = str(datetime.datetime.fromtimestamp(ts)) if ts else 'N/A'
        print(f"Line {idx} | Time: {time_str} | Data: {data}")
else:
    print("p_score_history.jsonl not found.")
