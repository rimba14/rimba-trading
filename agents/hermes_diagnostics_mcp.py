import os
import json
import time
import logging
import sys
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for Hermes
mcp = FastMCP("Sentinel Diagnostics")

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

DIAGNOSTICS_DIR = r"C:\Sentinel_Project\pending_diagnostics"
os.makedirs(DIAGNOSTICS_DIR, exist_ok=True)

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

@mcp.tool()
def get_pending_diagnostics() -> str:
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
    return json.dumps(diagnostics, indent=2)

@mcp.tool()
def resolve_diagnostic(filename: str) -> str:
    """Removes a diagnostic file from the queue once processed."""
    path = os.path.join(DIAGNOSTICS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return json.dumps({"status": "success", "message": f"Resolved {filename}"})
    return json.dumps({"status": "error", "message": "FILE_NOT_FOUND"})

@mcp.tool()
def apply_sre_patch(target_file: str, search_pattern: str, replacement_text: str) -> str:
    """
    Privileged SRE Mode: Autonomously patches code to fix mathematical or logical flaws.
    Authorized for use only when CONSTITUTION_BREACH is detected.
    """
    # Security: Restrict to project directory
    abs_path = os.path.abspath(target_file)
    if not abs_path.startswith("C:\\Sentinel_Project"):
        return json.dumps({"status": "error", "message": "PERMISSION_DENIED: Outside project scope"})
        
    if not os.path.exists(target_file):
        return json.dumps({"status": "error", "message": f"FILE_NOT_FOUND: {target_file}"})
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if search_pattern not in content:
            return json.dumps({"status": "error", "message": "PATTERN_NOT_FOUND"})
        
        new_content = content.replace(search_pattern, replacement_text)
        
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Send Webhook
        send_sre_webhook(target_file, "CODE_PATCH_APPLIED", f"Patched pattern: {search_pattern[:50]}...")
        
        return json.dumps({"status": "success", "message": f"PATCH_APPLIED: {target_file}"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

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

if __name__ == "__main__":
    mcp.run()
