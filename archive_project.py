import os
import requests
import re

ARTIFACT_DIR = r"C:\Users\Administrator\.gemini\antigravity\brain\12325980-a53b-4d3f-8c1d-135ccefcf2eb"
OBSIDIAN_API_KEY = "cf0b91fc67fc911e9173f1a976b65db49b33a0e6c46d5ba639c9e26c2931f09d"
BASE_URL = "http://127.0.0.1:27123"

def upload_file(obsidian_path, content):
    url = f"{BASE_URL}/vault/{obsidian_path}"
    headers = {
        "Authorization": f"Bearer {OBSIDIAN_API_KEY}",
        "Content-Type": "text/markdown"
    }
    r = requests.put(url, headers=headers, data=content.encode('utf-8'))
    if r.status_code in [200, 204]:
        print(f"Uploaded: {obsidian_path}")
    else:
        print(f"Failed {obsidian_path}: {r.status_code} - {r.text}")

def run_archive():
    files = os.listdir(ARTIFACT_DIR)
    
    # Filter for walkthroughs and final plans
    walkthroughs = [f for f in files if f.startswith("walkthrough_") and f.endswith(".md") and ".resolved" not in f]
    plans = [f for f in files if f.startswith("implementation_plan_") and f.endswith(".md") and ".resolved" not in f]
    
    # Sort them (roughly by phase/name)
    walkthroughs.sort()
    plans.sort()
    
    index_content = "# Project Sentinel v13.5: Master Development Log\n\n## 📝 Implementation Plans\n"
    
    for p in plans:
        with open(os.path.join(ARTIFACT_DIR, p), 'r', encoding='utf-8') as f:
            content = f.read()
        obs_name = f"Project_Sentinel_v13.5/Plans/{p}"
        upload_file(obs_name, content)
        index_content += f"- [[{obs_name}|{p.replace('implementation_plan_', '').replace('.md', '').title()}]]\n"
        
    index_content += "\n## ✅ Phase Walkthroughs\n"
    for w in walkthroughs:
        with open(os.path.join(ARTIFACT_DIR, w), 'r', encoding='utf-8') as f:
            content = f.read()
        obs_name = f"Project_Sentinel_v13.5/Walkthroughs/{w}"
        upload_file(obs_name, content)
        index_content += f"- [[{obs_name}|{w.replace('walkthrough_', '').replace('.md', '').title()}]]\n"
        
    # Include final task.md
    with open(os.path.join(ARTIFACT_DIR, "task.md"), 'r', encoding='utf-8') as f:
        task_content = f.read()
    upload_file("Project_Sentinel_v13.5/Status_Final_Task.md", task_content)
    index_content += f"\n## 📊 Final Project Status\n- [[Project_Sentinel_v13.5/Status_Final_Task.md|Task Checklist]]\n"
    
    # Include trade journal
    journal_path = r"C:\\Sentinel_Project\\rsi_trade_journal.json"
    if os.path.exists(journal_path):
        import json
        with open(journal_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        trades_list = data.get("trades", [])
        journal_md = "# Sentinel v13.5 Trade Archive\n\n| Symbol | Side | PNL | Time |\n| --- | --- | --- | --- |\n"
        for t in trades_list[-100:]: # Last 100 trades for brevity
            pnl = t.get('pnl_dollars', t.get('pnl', 0))
            side = t.get('type', 'EXIT')
            journal_md += f"| {t.get('symbol', 'N/A')} | {side} | {pnl:.2f} | {t.get('exit_time', 'N/A')} |\n"
        
        upload_file("Project_Sentinel_v13.5/Trade_Archive.md", journal_md)
        index_content += f"- [[Project_Sentinel_v13.5/Trade_Archive.md|Recent Trade Archive]]\n"

    upload_file("Project_Sentinel_v13.5/Master_Index.md", index_content)
    print("Project Archival to Obsidian Complete.")

if __name__ == "__main__":
    run_archive()
