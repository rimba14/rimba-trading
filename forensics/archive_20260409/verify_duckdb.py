import duckdb
import os

db_path = "C:\\Sentinel_Project\\position_thesis.json"
if os.path.exists(db_path):
    print(f"[*] Verifying {db_path}...")
    try:
        # High-stability SQL that works with map-style single JSON objects
        sql = f"SELECT UNNEST(main) FROM read_json_auto('{db_path}') AS t(main)"
        res = duckdb.query(sql).to_df()
        print("[+] SUCCESS: Sentinel Data-Link is ACTIVE.")
        print(res.head())
    except Exception as e:
        print(f"[!] FAILED: {e}")
else:
    print(f"[!] FAILED: {db_path} not found.")
