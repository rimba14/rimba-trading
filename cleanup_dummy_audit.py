import os

def cleanup_dummy_audit():
    log_path = r"C:\Sentinel_Project\cognition_bridge.json"
    if os.path.exists(log_path):
        os.remove(log_path)
        print("[CLEANUP] Dummy data wiped. Sentinel is ready for live trading.")
    else:
        print("[INFO] Cognition ledger is already clear or empty.")

if __name__ == "__main__":
    cleanup_dummy_audit()
