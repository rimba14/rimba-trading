import os
import sys

def get_directory_size(path):
    total_size = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_symlink(): continue
                if entry.is_file(follow_symlinks=False):
                    total_size += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total_size += get_directory_size(entry.path)
            except (PermissionError, FileNotFoundError):
                continue
    except (PermissionError, FileNotFoundError):
        pass
    return total_size

def analyze_drive(root_path):
    print(f"[*] Analyzing: {root_path}")
    results = []
    
    # Analyze direct children of root_path first to get 'Folder-Level' granularity
    try:
        for item in os.listdir(root_path):
            item_path = os.path.join(root_path, item)
            if os.path.islink(item_path): continue
            
            if os.path.isdir(item_path):
                total_size = 0
                for root, dirs, files in os.walk(item_path, followlinks=False):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if not os.path.islink(fp):
                                total_size += os.path.getsize(fp)
                        except FileNotFoundError: pass
                results.append((item_path, total_size))
            else:
                results.append((item_path, os.path.getsize(item_path)))
    except Exception as e:
        print(f"Critial scan failure: {e}")

    results.sort(key=lambda x: x[1], reverse=True)
    print("\n--- TOP 20 CONSUMERS ---")
    for path, size in results[:20]:
        print(f"{path}: {size / (1024**3):.2f} GB")

if __name__ == "__main__":
    target = "C:/Users/Administrator"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    analyze_drive(target)
