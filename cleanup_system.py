import os
import shutil
from datetime import datetime

def perform_cleanup():
    base_dir = "C:\\Sentinel_Project\\"
    forensics_dir = os.path.join(base_dir, "forensics")
    archive_dir = os.path.join(forensics_dir, "archive_" + datetime.now().strftime("%Y%m%d"))
    
    # Files to be archived (Diagnostics and temp scripts)
    junk_files = [
        "debug_groq.py",
        "audit_risk_math.py",
        "diagnose_sl_2.py",
        "insider_test.py",
        "test_gemma.py",
        "verify_duckdb.py",
        "weekly_forecast_temp.py",
        "audit_arctic.py",
        "remediate_stealth.py",
        "cleanup_sol.py",
        "verdict.txt" 
    ]
    
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        print(f"[*] Created Archive: {archive_dir}")

    count = 0
    for f in junk_files:
        src = os.path.join(base_dir, f)
        if os.path.exists(src):
            shutil.move(src, os.path.join(archive_dir, f))
            print(f"[CLEANUP] Archived: {f}")
            count += 1
            
    print(f"\n[DONE] System Hygiene Complete. {count} files migrated to forensics repository.")

if __name__ == "__main__":
    perform_cleanup()
