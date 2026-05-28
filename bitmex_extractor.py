import os
import requests
import pandas as pd

# The raw GitHub URLs for the repository
BASE_URL = "https://raw.githubusercontent.com/omgbbqhaxx/BTC-Trading-Since-2020/main/"
# Repurposed existing files to bypass CRC creation errors
SAVE_DIR = "C:\\Sentinel_Project\\"
FILES_MAP = {
    "api-v1-execution-tradeHistory.csv": "trades_ledger.csv",
    "api-v1-order.csv": "orders_ledger.csv"
}

def download_file(file_name):
    url = BASE_URL + file_name
    save_path = os.path.join(SAVE_DIR, FILES_MAP[file_name])
    
    print(f"[FETCH] Requesting {file_name}...")
    
    # Stream the request to handle large files safely
    try:
        response = requests.get(url, stream=True)
        
        if response.status_code == 200:
            print(f"[CONN] Connection established. Downloading to {save_path}...")
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"[OK] Download complete: {file_name}\n")
            return save_path
        else:
            print(f"[ERR] Error {response.status_code}: Failed to download {file_name}\n")
            return None
    except Exception as e:
        print(f"[FAIL] Request failed for {file_name}: {e}")
        return None

if __name__ == "__main__":
    print("==============================================")
    print("== INITIATING BITMEX ARCHIVE EXTRACTION     ==")
    print("==============================================\n")
    
    downloaded_paths = []
    
    # 1. Download the files
    for file in FILES_MAP.keys():
        path = download_file(file)
        if path:
            downloaded_paths.append(path)
            
    # 2. Verify the data with Pandas
    if len(downloaded_paths) == 2:
        print("==============================================")
        print("== DATA VERIFICATION                        ==")
        print("==============================================")
        
        try:
            # Load the execution ledger to ensure it isn't corrupted
            print("[BUSY] Loading Trade History into memory...")
            df_trades = pd.read_csv(downloaded_paths[0], low_memory=False)
            print(f"[OK] Trade History verified. Total Rows: {len(df_trades):,}")
            
            print("[BUSY] Loading Order History into memory...")
            df_orders = pd.read_csv(downloaded_paths[1], low_memory=False)
            print(f"[OK] Order History verified. Total Rows: {len(df_orders):,}")
            
            print("\n[OK] Pipeline ready for Episodic Memory and XGBoost injection.")
            
        except Exception as e:
            print(f"\n[FAIL] Pandas failed to read the CSV files. Error: {e}")
