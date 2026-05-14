def read_us2000_post():
    log_path = r"C:\sentinel_logs\fastapi_sniper_v2.log"
    targets = ["2026-05-12 14:17", "2026-05-12 14:18", "2026-05-12 14:19", "2026-05-12 14:20", "2026-05-12 14:21", "2026-05-12 14:22"]
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            if any(t in line for t in targets) and "US2000" in line:
                print(f"{idx}: {line.strip()}")

if __name__ == "__main__":
    read_us2000_post()
