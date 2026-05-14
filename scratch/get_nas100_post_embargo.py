def read_nas100_post():
    log_path = r"C:\sentinel_logs\fastapi_sniper_v2.log"
    targets = ["2026-05-12 11:46", "2026-05-12 11:47", "2026-05-12 11:48", "2026-05-12 11:49", "2026-05-12 11:50", "2026-05-12 11:51"]
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            if any(t in line for t in targets) and "NAS100" in line:
                print(f"{idx}: {line.strip()}")

if __name__ == "__main__":
    read_nas100_post()
