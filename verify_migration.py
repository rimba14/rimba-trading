import os

def verify():
    print("\n==============================================")
    print("== SENTINEL MIGRATION VERIFICATION          ==")
    print("==============================================\n")
    
    checks = {
        "Project Root": r"C:\Sentinel_Project",
        "Arctic DB": r"C:\sentinel_arctic",
        "Venv": r"C:\Sentinel_Project\venv",
        "Config": r"C:\Sentinel_Project\migration_config.json"
    }
    
    all_passed = True
    for label, path in checks.items():
        if os.path.exists(path):
            print(f"[PASS] {label} exists at {path}")
        else:
            print(f"[FAIL] {label} MISSING at {path}")
            all_passed = False
            
    if all_passed:
        print("\n[SUCCESS] All core directories found on C: drive.")
    else:
        print("\n[!] WARNING: Some components are missing.")

if __name__ == "__main__":
    verify()
