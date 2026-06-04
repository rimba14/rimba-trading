import csv
import os

target_tickets = {1314756980, 1314607796}

def search_csv(filepath):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return
    print(f"\n--- Searching in {os.path.basename(filepath)} ---")
    found_count = 0
    with open(filepath, mode='r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
            print(f"Headers: {headers}")
        except StopIteration:
            print("Empty file.")
            return
            
        ticket_cols = [i for i, h in enumerate(headers) if 'ticket' in h.lower() or 'deal' in h.lower() or 'order' in h.lower() or 'id' in h.lower()]
        print(f"Scanning columns: {[(i, headers[i]) for i in ticket_cols]}")
        
        for row in reader:
            match = False
            for col_idx in ticket_cols:
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    try:
                        # Direct or substring match
                        if any(str(tk) in val for tk in target_tickets):
                            match = True
                            break
                    except Exception:
                        pass
            if match:
                found_count += 1
                print(f"Row {reader.line_num}: {row}")
    print(f"Found {found_count} matches.")

search_csv("C:/Sentinel_Project/orders_ledger.csv")
search_csv("C:/Sentinel_Project/trades_ledger.csv")
