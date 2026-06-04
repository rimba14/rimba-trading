import os
import sys

def main():
    ticket = 1322005892
    ticket_str = str(ticket)
    symbol = "EURJPY"
    log_dir = r"C:\sentinel_logs"
    
    print(f"=== SEARCHING IN {log_dir} ===")
    for f in os.listdir(log_dir):
        fpath = os.path.join(log_dir, f)
        if os.path.isfile(fpath) and f.endswith(('.log', '.txt')):
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as file:
                    for line_num, line in enumerate(file, 1):
                        if ticket_str in line or symbol in line:
                            # Let's show all lines containing the ticket or EURJPY
                            # since these log files are exactly what we want.
                            print(f"{f}:{line_num} -> {line.strip()}")
            except Exception as e:
                print(f"Error reading {f}: {e}")

if __name__ == "__main__":
    main()
