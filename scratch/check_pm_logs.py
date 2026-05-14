def check_pm():
    log_path = r"C:\sentinel_logs\profit_manager_v20_4.log"
    import os
    if not os.path.exists(log_path):
        print("Log file does not exist.")
        return
        
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    matches = [line.strip() for line in lines if "US2000" in line or "1286047526" in line or "1286047548" in line]
    print(f"Total matches for US2000/tickets: {len(matches)}")
    for m in matches:
        clean_str = m.encode("ascii", "replace").decode("ascii")
        print(clean_str)
        
if __name__ == "__main__":
    check_pm()
