import os
import json
import time
import logging
import sys

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

DIAGNOSTICS_DIR = r"C:\Sentinel_Project\pending_diagnostics"
os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

def get_pending_diagnostics():
    """Polls the pending_diagnostics directory for new payloads."""
    files = [f for f in os.listdir(DIAGNOSTICS_DIR) if f.endswith('.json')]
    diagnostics = []
    for f in files:
        path = os.path.join(DIAGNOSTICS_DIR, f)
        try:
            with open(path, 'r') as file:
                data = json.load(file)
                data['_filename'] = f
                diagnostics.append(data)
        except Exception as e:
            logging.error(f"Failed to read diagnostic {f}: {e}")
    return diagnostics

def clear_diagnostic(filename):
    """Removes a diagnostic file from the queue."""
    path = os.path.join(DIAGNOSTICS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False

def apply_sre_patch(target_file, search_pattern, replacement_text):
    """
    Privileged SRE Mode: Autonomously patches code to fix mathematical or logical flaws.
    """
    if not os.path.exists(target_file):
        return {"status": "error", "message": f"FILE_NOT_FOUND: {target_file}"}
    
    try:
        with open(target_file, 'r') as f:
            content = f.read()
        
        if search_pattern not in content:
            return {"status": "error", "message": "PATTERN_NOT_FOUND"}
        
        new_content = content.replace(search_pattern, replacement_text)
        
        with open(target_file, 'w') as f:
            f.write(new_content)
        
        # Send Webhook
        send_sre_webhook(target_file, "CODE_PATCH_APPLIED", f"Patched pattern: {search_pattern[:50]}...")
        
        return {"status": "success", "message": f"PATCH_APPLIED: {target_file}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def send_sre_webhook(target, event, details):
    """Pushes an SRE Resolution Webhook to Discord."""
    try:
        import requests
        payload = {
            "embeds": [{
                "title": f"🛠️ SRE AUTO-RESOLUTION: {event}",
                "description": f"**Target:** `{target}`\n**Details:** {details}",
                "color": 0xFF5733, # Orange/Red for SRE actions
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except:
        pass

SHAP_DIAG_DIR = r"C:\Sentinel_Project\shap_diagnostics"

def monitor_concept_drift():
    """
    Directive 3: SRE Concept Drift Tripwire.
    Monitors SHAP diagnostics and blocks trades if models exhibit extreme dominance (>65%).
    """
    if not os.path.exists(SHAP_DIAG_DIR): return
    
    files = [f for f in os.listdir(SHAP_DIAG_DIR) if f.endswith('.json')]
    for f in files:
        path = os.path.join(SHAP_DIAG_DIR, f)
        try:
            with open(path, 'r') as file:
                payload = json.load(file)
            
            symbol = payload['symbol']
            weights = payload['weights']
            
            # Identify dominance
            dominant_feature = None
            max_weight = 0.0
            for feat, weight in weights.items():
                if abs(weight) > max_weight:
                    max_weight = abs(weight)
                    dominant_feature = feat
            
            if max_weight > 0.65:
                # CONCEPT_DRIFT_WARNING Triggered
                logging.warning(f"[SRE] CONCEPT DRIFT DETECTED for {symbol}: {dominant_feature} has {max_weight:.1%} dominance.")
                
                # Autonomously overwrite conviction to 0.0 to block Fast Loop
                try:
                    import git_arctic
                    store = git_arctic.get_arctic()
                    lib = store['oracle_cache']
                    
                    drift_df = pd.DataFrame([{
                        "primary_dir": 0, # FORCE HOLD
                        "meta_conviction": 0.0, # FORCE ZERO CONVICTION
                        "timestamp": time.time(),
                        "sre_block": True,
                        "drift_feature": dominant_feature
                    }])
                    lib.write(f"{symbol}_meta", drift_df)
                    
                    # Notify Discord
                    send_drift_webhook(symbol, dominant_feature, max_weight)
                except Exception as ex:
                    logging.error(f"Failed to apply Drift Block for {symbol}: {ex}")
            
            # Clear diagnostic after processing to prevent loops
            os.remove(path)
            
        except Exception as e:
            logging.error(f"Error parsing SHAP diagnostic {f}: {e}")

def send_drift_webhook(symbol, feature, weight):
    """Pushes a Concept Drift Halt Webhook."""
    try:
        import requests
        from datetime import datetime
        payload = {
            "embeds": [{
                "title": "🚨 SRE TRIPWIRE: CONCEPT DRIFT HALT",
                "description": (
                    f"**Symbol:** `{symbol}`\n"
                    f"**Status:** `TRADING_BLOCKED (Conviction 0.0)`\n"
                    f"**Dominant Feature:** `{feature}`\n"
                    f"**Weight:** `{weight:.1%}`\n"
                    f"**Analysis:** Single feature dominance exceeded 65%. Signal likely corrupted or overfit to noise."
                ),
                "color": 0xFF0000,
                "timestamp": datetime.utcnow().isoformat()
            }]
        }
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except:
        pass

if __name__ == "__main__":
    import pandas as pd
    logging.basicConfig(level=logging.INFO)
    print("[*] Hermes Diagnostics Monitoring Active...")
    while True:
        monitor_concept_drift()
        time.sleep(1)
