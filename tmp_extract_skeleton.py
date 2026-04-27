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
                    if isinstance(subitem, ast.FunctionDef):
                        args = ast.unparse(subitem.args)
                        skeleton.append(f"  DEF: {subitem.name}({args})")
            elif isinstance(item, ast.FunctionDef):
                args = ast.unparse(item.args)
                skeleton.append(f"DEF: {item.name}({args})")
        return skeleton
    except Exception as e:
        return [f"ERR: {e}"]

def main():
    py_files = []
    for root, dirs, files in os.walk("C:\\Sentinel_Project\\\"):
        if any(x in root for x in [".venv", "venv", "__pycache__", ".git", ".agents", ".gemini", "AITEMP", "Program Files", "Windows"]):
            continue
        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))
    
    with open("C:\\Sentinel_Project\\\architecture_skeleton.txt", "w", encoding="utf-8") as f:
        for py_file in sorted(py_files):
            rel_path = os.path.relpath(py_file, "C:\\Sentinel_Project\\\")
            f.write(f"\nFILE: {rel_path}\n")
            # Heuristic for purpose: first docstring or first 100 chars
            try:
                with open(py_file, "r", encoding="utf-8") as pf:
                    first_line = pf.readline().strip()
                    if first_line.startswith('"""') or first_line.startswith("'''"):
                        f.write(f"PURPOSE: {first_line.strip('\"\'')}\n")
                    else:
                        f.write(f"PURPOSE: Python script {file}\n")
            except:
                f.write("PURPOSE: Unknown\n")
            
            skeleton = get_skeleton(py_file)
            for line in skeleton:
                f.write(f"{line}\n")

if __name__ == "__main__":
    main()
