import os
import json
import shutil
import subprocess
import logging
import sys
import time
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for SRE Watchdog
mcp = FastMCP("Sentinel SRE Watchdog")

# --- CONFIGURATION ---
LOG_DIR = r"C:\sentinel_logs"
CONSTITUTION_PATH = r"C:\Sentinel_Project\Master_Prompt.txt"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1496246026611458048/2ShGeHJjN-Z6XrydLjFy_hOz-iLWrqNHVfp3vanWHj7udTYXUGfglWvUdxJ0WqLyAK88"

# Service Log Mapping
SERVICE_LOGS = {
    "slow_loop": os.path.join(LOG_DIR, "slow_loop.log"),
    "fast_loop": os.path.join(LOG_DIR, "fast_loop_v15.log"),
    "hermes": r"C:\Sentinel_Project\hermes_orchestrator.log",
    "profit_manager": os.path.join(LOG_DIR, "profit_manager.log")
}

class SRENotifier:
    def __init__(self, webhook_url=DISCORD_WEBHOOK):
        self.webhook_url = webhook_url

    def send_intervention_alert(self, message: str):
        if not self.webhook_url: return
        try:
            import requests
            payload = {
                "content": "⚠️ **SENTINEL SRE WATCHDOG INTERVENTION**",
                "embeds": [{
                    "title": "System Self-Healing Event",
                    "description": message,
                    "color": 16776960, # Yellow/Warning
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }]
            }
            requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception as e:
            logging.error(f"SRE Webhook Exception: {e}")

notifier = SRENotifier()

@mcp.tool()
def analyze_traceback(service_name: str) -> str:
    """
    SRE Tool: Reads the last 50 lines of a service log to extract Python tracebacks.
    """
    log_path = SERVICE_LOGS.get(service_name.lower())
    if not log_path or not os.path.exists(log_path):
        return f"Error: Log for service '{service_name}' not found at {log_path}"

    try:
        with open(log_path, "r", encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-50:]
        return "".join(lines)
    except Exception as e:
        return f"Error reading log: {str(e)}"

@mcp.tool()
def patch_codebase(file_path: str, old_code_block: str, new_code_block: str) -> str:
    """
    SRE Tool: Surgically patches a Python script. Creates a .bak backup before saving.
    """
    if not os.path.exists(file_path):
        return f"Error: File {file_path} not found."

    try:
        # Create Backup (Directive 1)
        shutil.copy2(file_path, file_path + ".bak")
        
        with open(file_path, "r", encoding='utf-8') as f:
            content = f.read()
            
        if old_code_block not in content:
            return "Error: Exact code block to replace not found in target file."
            
        new_content = content.replace(old_code_block, new_code_block)
        
        with open(file_path, "w", encoding='utf-8') as f:
            f.write(new_content)
            
        notifier.send_intervention_alert(f"Successfully patched `{file_path}`. Backup created as `.bak`.")
        return f"Patch Applied successfully to {file_path}. Backup created."
        
    except Exception as e:
        return f"Error during patching: {str(e)}"

@mcp.tool()
def restart_service(service_name: str) -> str:
    """
    SRE Tool: Gracefully restarts a Sentinel microservice.
    Supports: slow_loop, fast_loop, hermes, profit_manager.
    """
    # Mapping service names to their specific python commands
    commands = {
        "slow_loop": "python sentinel_slow_loop.py",
        "fast_loop": "python chat_gemma.py",
        "hermes": "python hermes_orchestrator.py",
        "profit_manager": "python agents/profit_manager_v15.py"
    }
    
    cmd = commands.get(service_name.lower())
    if not cmd:
        return f"Error: No restart command defined for service '{service_name}'."

    try:
        # 1. Terminate existing (Self-Healing logic)
        # We look for the python process that has the script name in its command line
        kill_cmd = f"wmic process where \"commandline like '%{service_name}%'\" delete"
        # Fallback for systems without wmic: taskkill based on string match isn't native, 
        # so we'll use a python subprocess loop if needed.
        
        # 2. Restart (Directive 1)
        # Using 'start' to run in a new detached window
        restart_cmd = f"cmd.exe /c start \"SENTINEL RESTART: {service_name}\" /D \"C:\\Sentinel_Project\" cmd /k \"call venv\\Scripts\\activate && {cmd}\""
        subprocess.Popen(restart_cmd, shell=True)
        
        notifier.send_intervention_alert(f"Restarted service `{service_name}` via background watchdog.")
        return f"Service {service_name} restart initiated."
        
    except Exception as e:
        return f"Error during restart: {str(e)}"

@mcp.tool()
def update_constitution(new_prompt_text: str) -> str:
    """
    SRE Tool: Overwrites the Master Constitution with updated system rules.
    """
    try:
        with open(CONSTITUTION_PATH, "w", encoding='utf-8') as f:
            f.write(new_prompt_text)
        return "Master Constitution updated successfully."
    except Exception as e:
        return f"Error updating constitution: {str(e)}"

if __name__ == "__main__":
    mcp.run()
