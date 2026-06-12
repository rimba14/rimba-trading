import os
import sys
import time
import json
import re
import requests

# Add paths to make sure we can import sentinel modules
sys.path.append(r"C:\Users\ADMIN\.antigravity\rimba-trading")
sys.path.append(r"C:\Sentinel_Project")

import sentinel_config as cfg

DIAG_DIR = r"C:\Users\ADMIN\.antigravity\rimba-trading\pending_diagnostics"
if not os.path.exists(DIAG_DIR):
    DIAG_DIR = r"C:\Sentinel_Project\pending_diagnostics"

OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/generate"
MODEL_ID = "qwen2.5-coder:3b"

def mathematical_verification_underwriter(healed_code_block: str, original_code_block: str) -> bool:
    """Gated verification underwriter: ensures healed block compiles and preserves basic syntax structure."""
    try:
        # 1. Compile test
        compile(healed_code_block, "<string>", "exec")
        
        # 2. Check that the healed block doesn't introduce massive changes (e.g. it is still within 20 lines)
        if len(healed_code_block.splitlines()) > len(original_code_block.splitlines()) + 5:
            print("[UNDERWRITER_REJECT] Healed block size deviates too much from original.")
            return False
            
        return True
    except Exception as e:
        print(f"[UNDERWRITER_REJECT] Verification failed: {e}")
        return False

def query_ollama_for_heal(error_msg: str, original_block: str) -> str:
    """Calls Ollama to heal the specific code block based on the error message."""
    system_prompt = (
        "You are an AST code-healing agent. Your task is to fix a small block of Python code to resolve a specific error.\n"
        "Return ONLY the fixed code block. Do NOT include markdown code blocks (```python ... ```), explanations, or introduction.\n"
        "Keep the exact indentation and variable names of the surrounding code."
    )
    user_prompt = (
        f"Error Message:\n{error_msg}\n\n"
        f"Original Code Block:\n{original_block}\n\n"
        "Fixed Code Block:"
    )
    
    payload = {
        "model": MODEL_ID,
        "prompt": f"{system_prompt}\n\n{user_prompt}",
        "stream": False,
        "options": {
            "temperature": 0.05,
            "num_thread": 4,
            "num_ctx": 1024,
        }
    }
    try:
        resp = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json().get("response", "").strip()
            # Remove any markdown wrapping if returned by mistake
            if result.startswith("```python"):
                result = result[9:]
            if result.endswith("```"):
                result = result[:-3]
            return result.strip()
    except Exception as e:
        print(f"[SRE_OLLAMA_ERR] Failed to communicate with Ollama: {e}")
    return ""

def heal_exception_file(diag_file, diag_data):
    traceback_str = diag_data.get("traceback", "")
    error_msg = diag_data.get("message", "")
    
    # Extract filename and line number from traceback (last occurrence)
    # Matches: File "path/to/file.py", line 123
    matches = re.findall(r'File "([^"]+)", line (\d+)', traceback_str)
    if not matches:
        print(f"[SRE_HEAL_SKIP] Could not parse traceback for {diag_file}")
        return False
        
    raw_path, line_num_str = matches[-1]
    line_num = int(line_num_str)
    
    # Resolve physical file path: map virtual paths to local workspace paths if needed
    target_path = raw_path
    if "C:\\Sentinel_Project" in raw_path:
        local_path = raw_path.replace("C:\\Sentinel_Project", r"C:\Users\ADMIN\.antigravity\rimba-trading")
        if os.path.exists(local_path):
            target_path = local_path
            
    if not os.path.exists(target_path):
        print(f"[SRE_HEAL_SKIP] Target file {target_path} does not exist.")
        return False
        
    print(f"[SRE_HEALING] Healing {target_path} at line {line_num} for error: {error_msg}")
    
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Extract 10 lines before and after (total ~20 lines max)
        start_idx = max(0, line_num - 11)
        end_idx = min(len(lines), line_num + 9)
        
        original_block = "".join(lines[start_idx:end_idx])
        
        # Query Ollama for fixed block
        healed_block = query_ollama_for_heal(error_msg, original_block)
        if not healed_block:
            print("[SRE_HEAL_FAIL] Ollama returned empty response.")
            return False
            
        # Mathematical verification underwriter
        if not mathematical_verification_underwriter(healed_block, original_block):
            return False
            
        # Reconstruct the file contents
        new_lines = lines[:start_idx] + [healed_block + "\n"] + lines[end_idx:]
        
        # Atomic write
        temp_path = target_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        os.replace(temp_path, target_path)
        
        print(f"[SRE_HEAL_SUCCESS] Successfully patched {target_path} at line {line_num}!")
        return True
    except Exception as e:
        print(f"[SRE_HEAL_FAIL] Failed to apply patch: {e}")
        return False

def main():
    print("[SRE_DAEMON] Starting Autonomous SRE Self-Healing Watchdog...")
    
    if "--test-dry-run" in sys.argv:
        print("[SRE_DAEMON] Running dry-run validation step...")
        # Create a mock diagnostic file if none exists for test purposes
        mock_file = os.path.join(DIAG_DIR, "fatal_error_mock_test.json")
        mock_data = {
            "timestamp": int(time.time()),
            "symbol": "EURUSD",
            "error_type": "NameError",
            "message": "name 'math' is not defined",
            "traceback": 'Traceback (most recent call last):\n  File "C:\\Sentinel_Project\\sentinel_slow_loop.py", line 12,\n    W_time = math.exp(-0.02)\nNameError: name \'math\' is not defined\n',
            "halt_required": True
        }
        os.makedirs(DIAG_DIR, exist_ok=True)
        with open(mock_file, "w") as f:
            json.dump(mock_data, f)
            
        # Test loading and healing
        with open(mock_file, "r") as f:
            data = json.load(f)
        # SRE logic should extract but skip since file path in mock might not exist or we mock compile
        print("[SRE_DAEMON] Dry-run parsing mock error json...")
        matches = re.findall(r'File "([^"]+)", line (\d+)', data["traceback"])
        assert len(matches) > 0, "Failed to parse traceback in mock"
        print("[SRE_DAEMON] Mock parsing verified. Deleting mock test file.")
        os.remove(mock_file)
        return

    while True:
        try:
            if os.path.exists(DIAG_DIR):
                for filename in os.listdir(DIAG_DIR):
                    if filename.startswith("fatal_error_") and filename.endswith(".json"):
                        filepath = os.path.join(DIAG_DIR, filename)
                        try:
                            with open(filepath, "r") as f:
                                diag_data = json.load(f)
                            success = heal_exception_file(filepath, diag_data)
                            if success:
                                # Remove diagnostic ticket once healed
                                os.remove(filepath)
                                print(f"[SRE_DAEMON] Resolved and cleared ticket {filename}")
                        except Exception as file_err:
                            print(f"[SRE_DAEMON_ERR] Failed to process ticket {filename}: {file_err}")
                            
        except Exception as e:
            print(f"[SRE_DAEMON_ERR] Watchdog loop exception: {e}")
            
        time.sleep(10)

if __name__ == "__main__":
    main()
