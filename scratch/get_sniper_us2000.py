def read_sniper_us2000():
    log_path = r"C:\sentinel_logs\fastapi_sniper_v2.log"
    target_time = "2026-05-11 20:21"
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            if target_time in line:
                print(f"{idx}: {line.strip()}")

if __name__ == "__main__":
    read_sniper_us2000()
