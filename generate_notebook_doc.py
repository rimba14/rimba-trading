import os

# Configuration
ROOT_DIR = r"C:\Sentinel_Project"
OUTPUT_FILE = os.path.join(ROOT_DIR, "Adaptive_Sentinel_Source.md")
EXTENSIONS = {'.py', '.json', '.bat', '.toml'}
EXCLUDE_DIRS = {
    'venv', '__pycache__', 'bitmex_archive', 'arctic_db', 'hft_data', 
    'zipline_data', 'backtest', 'SentinelHub', 'programs', '.archon', 
    '.lmstudio', '.ollama', 'Bluestacks', 'Config.Msi', 'Intel', 
    'NASA_POLYMARKET', 'Obsidian', 'PerfLogs', 'Recovery', 'Superwhisper',
    'system_archive', 'found.000', 'found.001', 'boot', 'bin'
}
MAX_JSON_SIZE_KB = 500  # Skip massive JSON data dumps

def generate_notebook_doc():
    files_to_process = []
    
    print(f"[*] Scanning {ROOT_DIR}...")
    
    for root, dirs, files in os.walk(ROOT_DIR):
        # Filter directories: exclude specific names and hidden folders
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and 'arctic' not in d.lower() and not d.startswith('.')]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in EXTENSIONS:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, ROOT_DIR)
                
                # Special handling for JSON size
                if ext == '.json':
                    if os.path.getsize(full_path) > MAX_JSON_SIZE_KB * 1024:
                        print(f"[!] Skipping large JSON: {rel_path}")
                        continue
                
                files_to_process.append((rel_path, full_path))

    # Sort files for a consistent TOC
    files_to_process.sort()

    markdown_content = []
    markdown_content.append("# Adaptive Sentinel Source Codebase")
    markdown_content.append("\n## Table of Contents")
    for rel_path, _ in files_to_process:
        markdown_content.append(f"- [{rel_path}](#{rel_path.replace('.', '').replace('/', '').replace('\\', '').lower()})")
    
    markdown_content.append("\n---\n")

    for rel_path, full_path in files_to_process:
        print(f"[*] Processing {rel_path}...")
        markdown_content.append(f"## /{rel_path.replace('\\', '/')}")
        
        ext = os.path.splitext(rel_path)[1].lower()
        lang = "python" if ext == ".py" else ("json" if ext == ".json" else "bash")
        
        markdown_content.append(f"````{lang}")
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                markdown_content.append(content)
        except Exception as e:
            markdown_content.append(f"ERROR READING FILE: {e}")
        
        markdown_content.append("````\n")

    print(f"[*] Writing to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(markdown_content))
    
    print("[SUCCESS] NotebookLM ingestion document generated.")

if __name__ == "__main__":
    generate_notebook_doc()
