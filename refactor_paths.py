import os
import re

def refactor_paths(root_dir):
    """
    Scans all .py, .bat, and .json files in root_dir and replaces
    legacy C:\\Sentinel_Project\\ or C:\\Sentinel_Project\\ paths with the new C:\ equivalents.
    """
    
    # Path mappings
    replacements = {
        r'E:[\\/]arctic_db': r'C:\\sentinel_arctic',
        r'E:[\\/]': r'C:\\Sentinel_Project\\'
    }
    
    extensions = ('.py', '.bat', '.json')
    
    print(f"[*] Starting path refactor in: {root_dir}")
    
    for root, dirs, files in os.walk(root_dir):
        # Skip certain directories
        if any(skip in root for skip in ['venv', '.git', '__pycache__']):
            continue
            
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    original_content = content
                    for pattern, replacement in replacements.items():
                        content = re.sub(pattern, replacement.replace('\\', '\\\\'), content, flags=re.IGNORECASE)
                    
                    if content != original_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"[REFACTORED] {file_path}")
                except Exception as e:
                    print(f"[!] Error processing {file_path}: {e}")

if __name__ == "__main__":
    target = r"C:\Sentinel_Project"
    if os.path.exists(target):
        refactor_paths(target)
    else:
        print(f"[!] Target directory {target} not found.")
