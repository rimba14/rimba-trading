import pandas as pd
import numpy as np
from arcticdb import Arctic
from datetime import datetime

def transmute_arctic_to_hft(symbol, output_path):
    """
    Converts ArcticDB L1 Tick data into hftbacktest-compatible L2 format.
    Since we only have L1 (best bid/ask), we simulate a single level of depth.
    """
    print(f"[DATA_HFT] Reading {symbol} from ArcticDB...")
    try:
        ac = Arctic("lmdb://C:\\sentinel_arctic")
        lib = ac.get_library("trading_data")
        df = lib.read(symbol).data
    except Exception as e:
        print(f"[DATA_HFT] Error: {e}")
        return

    # hftbacktest format: [timestamp, event_type, side, price, qty]
    # event_type: 1 (Add), 2 (Modify), 3 (Delete) or often simplified
    # For L1 simulation, we just use local timestamps and price updates.
    
    hft_data = []
    # hftbacktest timestamp is in microseconds
    for idx, row in df.iterrows():
        ts_micro = int(idx.timestamp() * 1_000_000)
        
        # Best Bid
        if row['bid'] > 0:
            hft_data.append([ts_micro, 1, 1, row['bid'], 100000]) # Side 1 = Bid
        # Best Ask
        if row['ask'] > 0:
            hft_data.append([ts_micro, 1, -1, row['ask'], 100000]) # Side -1 = Ask
            
    hft_df = pd.DataFrame(hft_data, columns=['timestamp', 'event_type', 'side', 'price', 'qty'])
    hft_df.sort_values('timestamp', inplace=True)
    
    # Save as .npz (hftbacktest native)
    np.savez_compressed(output_path, data=hft_df.values)
    print(f"[DATA_HFT] Transmuted {len(hft_df)} events to {output_path}")

if __name__ == "__main__":
    import os
    if not os.path.exists("C:\\Sentinel_Project\\hft_data"):
        os.makedirs("C:\\Sentinel_Project\\hft_data")
    transmute_arctic_to_hft("EURUSD_TICKS", "C:\\Sentinel_Project\\hft_data/EURUSD_L2.npz")
