import re
import sys
from pathlib import Path

def main():
    print("==================================================")
    print(" [LEAKAGE SHIELD] SCANNING FOR LOOKAHEAD BIAS")
    print("==================================================")
    
    target_file = Path(r"C:\Sentinel_Project\feature_engineering.py")
    if not target_file.exists():
        print(f" [FAIL] Target file not found: {target_file}")
        sys.exit(1)
        
    code = target_file.read_text(encoding="utf-8")
    lines = code.splitlines()
    
    violations = []
    
    # 1. Regex hunt for .bfill()
    bfill_pattern = re.compile(r"\.bfill\(")
    # 2. Regex hunt for negative shifts (e.g. .shift(-1))
    shift_neg_pattern = re.compile(r"\.shift\(\s*-\s*\d+")
    
    for idx, line in enumerate(lines):
        line_num = idx + 1
        # Strip comments to prevent false positives in commented out code
        code_part = line.split("#")[0].strip()
        
        if bfill_pattern.search(code_part):
            violations.append((line_num, line.strip(), "Lookahead Backfill (.bfill)"))
            
        if shift_neg_pattern.search(code_part):
            violations.append((line_num, line.strip(), "Negative Shift (.shift(-n))"))
            
    if violations:
        print(f" [FAIL] {len(violations)} Data Leakage / Lookahead violations detected!")
        for l_num, content, reason in violations:
            print(f"   Line {l_num}: {reason} -> '{content}'")
        print(" [CRITICAL] CI/CD pipeline blocked due to lookahead bias risk.")
        print("==================================================")
        sys.exit(1)
        
    print(" [PASS] Anti-leakage checks completed. Zero lookahead bias patterns detected!")
    print("==================================================")
    sys.exit(0)

if __name__ == "__main__":
    main()
