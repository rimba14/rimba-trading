try:
    from arcticdb import Arctic
    import pandas as pd
    import numpy as np

    institutional_ledger = None

    def get_arctic():
        global institutional_ledger
        if institutional_ledger is None:
            # Directive: Synchronized LMDB Cache
            uri = "lmdb://./data/arctic_cache"
            institutional_ledger = Arctic(uri)
        return institutional_ledger

    def test_arctic():
        try:
            ac = get_arctic()
            libs = ac.list_libraries()
            print(f"[SUCCESS] Connected to ArcticDB. Found libraries: {libs}")
            
            if "migration_test" not in libs:
                ac.create_library("migration_test")
                print("[*] Created 'migration_test' library.")
            
            lib = ac["migration_test"]
            df = pd.DataFrame({'test': [1, 2, 3]}, index=pd.date_range('2026-01-01', periods=3))
            lib.write("test_symbol", df)
            
            read_df = lib.read("test_symbol").data
            if read_df.equals(df):
                print("[SUCCESS] Data write/read verification passed.")
            
            ac.delete_library("migration_test")
            print("[*] Cleaned up test library.")
            
        except Exception as e:
            print(f"[FAIL] ArcticDB Error: {e}")

    if __name__ == "__main__":
        test_arctic()

except ImportError:
    print("[!] ArcticDB not installed in current environment. Please ensure venv is activated.")
