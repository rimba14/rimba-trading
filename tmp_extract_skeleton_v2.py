import os
import ast

def get_skeleton(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            node = ast.parse(f.read())
        
        skeleton = []
        for item in node.body:
            if isinstance(item, ast.ClassDef):
                skeleton.append(f"CLASS: {item.name}")
                for subitem in item.body:
                    if isinstance(subitem, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = ast.unparse(subitem.args)
                        skeleton.append(f"  DEF: {subitem.name}({args})")
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = ast.unparse(item.args)
                skeleton.append(f"DEF: {item.name}({args})")
        return skeleton
    except Exception as e:
        return [f"ERR: {e}"]

def main():
    # Only scan active development folders and root
    include_dirs = ["agents", "strategies", "NASA_POLYMARKET", "SentinelHub", "forensics"]
    files_to_scan = []
    
    # Root files
    for f in os.listdir("C:\\Sentinel_Project\\\"):
        if f.endswith(".py") and os.path.isfile(os.path.join("C:\\Sentinel_Project\\\", f)):
            files_to_scan.append(os.path.join("C:\\Sentinel_Project\\\", f))
            
    # Subdir files
    for d in include_dirs:
        dir_path = os.path.join("C:\\Sentinel_Project\\\", d)
        if os.path.exists(dir_path):
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.endswith(".py"):
                        files_to_scan.append(os.path.join(root, f))
    
    with open("C:\\Sentinel_Project\\\architecture_skeleton_v2.txt", "w", encoding="utf-8") as f:
        for py_file in sorted(files_to_scan):
            rel_path = os.path.relpath(py_file, "C:\\Sentinel_Project\\\")
            f.write(f"\nFILE: {rel_path}\n")
            try:
                with open(py_file, "r", encoding="utf-8") as pf:
                    first_line = pf.readline().strip()
                    if first_line.startswith('"""') or first_line.startswith("'''"):
                        f.write(f"PURPOSE: {first_line.strip('\"\'')}\n")
                    else:
                        f.write(f"PURPOSE: Python script {os.path.basename(py_file)}\n")
            except:
                f.write("PURPOSE: Unknown\n")
            
            skeleton = get_skeleton(py_file)
            for line in skeleton:
                f.write(f"{line}\n")

if __name__ == "__main__":
    main()
