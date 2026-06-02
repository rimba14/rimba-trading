import os
import sys

def main():
    ticket = 1322005892
    ticket_str = str(ticket)
    symbol = "EURJPY"
    log_dir = r"C:\sentinel_logs"
    out_path = r"C:\Sentinel_Project\scratch\eurjpy_forensics.txt"
    
    print(f"Filtering logs for {symbol} and ticket {ticket}...")
    
    with open(out_path, "w", encoding="utf-8") as out:
        for f in os.listdir(log_dir):
            fpath = os.path.join(log_dir, f)
            if os.path.isfile(fpath) and f.endswith(('.log', '.txt')):
                out.write(f"\n=========================================\n")
                out.write(f"FILE: {f}\n")
                out.write(f"=========================================\n")
                try:
                    count = 0
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as file:
                        for line_num, line in enumerate(file, 1):
                            # Search for lines containing our ticket, or EURJPY on 2026-05-19 between 17:40 and 18:40
                            has_ticket = ticket_str in line
                            has_eurjpy_time = (symbol in line) and ("2026-05-19 17:" in line or "2026-05-19 18:" in line or "2026-05-19 20:" in line or "2026-05-19 21:" in line)
                            
                            if has_ticket or has_eurjpy_time:
                                out.write(f"Line {line_num}: {line}")
                                count += 1
                    print(f"Found {count} matching lines in {f}")
                except Exception as e:
                    out.write(f"Error reading {f}: {e}\n")
                    
    print(f"Results written to {out_path}")

if __name__ == "__main__":
    main()
