import os
import sys

def main():
    ticket = 1322005892
    ticket_str = str(ticket)
    log_dir = r"C:\sentinel_logs"
    
    print(f"=== SEARCHING SPECIFIC TICKET {ticket} IN LOGS ===")
    found = False
    for f in os.listdir(log_dir):
        fpath = os.path.join(log_dir, f)
        if os.path.isfile(fpath) and f.endswith(('.log', '.txt')):
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as file:
                    for line_num, line in enumerate(file, 1):
                        if ticket_str in line:
                            print(f"{f}:{line_num} -> {line.strip()}")
                            found = True
            except Exception as e:
                print(f"Error reading {f}: {e}")
    if not found:
        print("Ticket not found in any log files in C:\\sentinel_logs.")

if __name__ == "__main__":
    main()
