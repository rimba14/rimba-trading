def read_log_context():
    log_path = r"C:\sentinel_logs\slow_loop_v17_9.log"
    target = "0.573322"
    buffer = []
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            buffer.append((idx, line.strip()))
            if len(buffer) > 120:
                buffer.pop(0)
            if target in line:
                with open(r"C:\Sentinel_Project\scratch\slow_log_buffer.txt", "w", encoding="utf-8") as out:
                    for ln_num, ln in buffer:
                        out.write(f"{ln_num}: {ln}\n")
                print("Saved buffer to scratch/slow_log_buffer.txt")
                break

if __name__ == "__main__":
    read_log_context()
