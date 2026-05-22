import requests
import datetime
import json
import os

OBSIDIAN_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")
BASE_URL = os.environ.get("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")

def log_event(path, content, mode="append"):
    """
    Logs an event to the specified path in the Obsidian vault.
    """
    url = f"{BASE_URL}/vault/{path}"
    headers = {
        "Authorization": f"Bearer {OBSIDIAN_API_KEY}",
        "Content-Type": "text/markdown"
    }
    
    if mode == "append":
        # Check if file exists to decide whether to use PUT or POST
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            # File exists, append with newline
            current_content = r.text
            new_content = current_content + "\n" + content
            requests.put(url, headers=headers, data=new_content)
        else:
            # File doesn't exist, create it
            requests.put(url, headers=headers, data=content)
    else:
        # Overwrite/Create
        requests.put(url, headers=headers, data=content)

def log_regime_shift(symbol, features):
    """
    Creates a detailed research note for a Wavelet-detected regime shift.
    """
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    path = f"Research/Regime_Shifts_{date_str}.md"
    
    # Extract wavelet info from features
    dom_scale = features.get('w_dom_scale', 0) * 32.0
    max_pow = features.get('w_max_pow', 0) * 10.0
    anomaly = features.get('_anomaly_score', 0)
    
    content = f"""
## [{time_str}] Regime Shift Detected: {symbol}
- **Dominant Scale**: {dom_scale:.2f}
- **Max Spectral Power**: {max_pow:.4f}
- **Anomaly Score**: {anomaly:.4f}
- **Status**: Exploration Entropy Boosted (+2.0)

### Feature Vector (Partial)
```json
{json.dumps({k: v for k, v in features.items() if k.startswith('w_')}, indent=2)}
```
---
"""
    log_event(path, content, mode="append")
    print(f"[OBSIDIAN] Logged shift for {symbol} to {path}")

def init_vault_structure():
    """Ensures folders exist."""
    # Local REST API doesn't have a direct "mkdir", but creating a file in a subfolder 
    # usually creates the folder structure in Obsidian.
    log_event("Research/.keep", "Folder marker", mode="overwrite")
