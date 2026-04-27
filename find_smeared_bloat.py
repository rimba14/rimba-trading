import os
import sys

def analyze_profile(root_path):
    print(f"[*] Analyzing Smeared Bloat in: {root_path}")
    results = []
    
    try:
        for item in os.listdir(root_path):
            ip = os.path.join(root_path, item)
            if os.path.islink(ip): continue
            
            if os.path.isdir(ip):
                count = 0
                total_size = 0
                for root, dirs, files in os.walk(ip, followlinks=False):
                    count += len(files)
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if not os.path.islink(fp):
                                total_size += os.path.getsize(fp)
                        except: pass
                results.append((ip, total_size, count))
            else:
                results.append((ip, os.path.getsize(ip), 1))
    except Exception as e:
        print(f"Error: {e}")

    results.sort(key=lambda x: x[1], reverse=True)
    print("\n--- TOP 20 CONSUMERS (DIR SIZE) ---")
    for path, size, count in results[:20]:
        print(f"{path}: {size / (1024**3):.2f} GB ({count} files)")

if __name__ == "__main__":
    analyze_profile("C:/Users/Administrator")
