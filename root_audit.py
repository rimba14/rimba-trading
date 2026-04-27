import os

def get_dir_size(path):
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(entry.path)
    except (PermissionError, FileNotFoundError):
        pass
    return total

root = "C:/"
print(f"[*] Auditing Root: {root}")
results = []
try:
    with os.scandir(root) as it:
        for entry in it:
            if entry.is_dir(follow_symlinks=False):
                size = get_dir_size(entry.path)
                results.append((entry.path, size))
            else:
                results.append((entry.path, entry.stat().st_size))
except Exception as e:
    print(f"Error: {e}")

results.sort(key=lambda x: x[1], reverse=True)
print("\n--- ROOT CONSUMERS ---")
for p, s in results[:20]:
    print(f"{p}: {s/1024/1024/1024:.2f} GB")
