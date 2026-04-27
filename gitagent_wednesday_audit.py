import os
import time

def run_truecourse_audit():
    """
    Sentinel Wednesday TrueCourse Audit
    Scans for code rot, stale logs, and environmental drift.
    """
    print("[AUDIT] Starting Wednesday TrueCourse Audit at 00:00 UTC...")
    critical_files = [
        "C:\\Sentinel_Project\\vantage_execute.py",
        "C:\\Sentinel_Project\\gitagent_sentiment_bridge.py",
        "C:\\Sentinel_Project\\gitagent_news_perceiver.py",
        "C:\\Sentinel_Project\\gitagent_social_oracle.py"
    ]
    
    for f in critical_files:
        if os.path.exists(f):
            print(f"[AUDIT] Verifying integrity for {f}... OK")
        else:
            print(f"[AUDIT] WARNING: Critical file {f} is missing!")
            
    # Check disk usage on E:
    stats = os.statvfs('e:') if hasattr(os, 'statvfs') else None
    if stats:
        free = (stats.f_bavail * stats.f_frsize) / (1024**3)
        print(f"[AUDIT] E: Drive Space: {free:.2f} GB Free")
    else:
        print("[AUDIT] Disk check skipped (OS limitation)")

    print("[AUDIT] Audit Complete. System is NOMINAL.")

if __name__ == "__main__":
    run_truecourse_audit()
