import time
import pandas as pd
import numpy as np
import timesfm_bridge

print("[TIMING] Starting 1 inference...")
test_df = pd.DataFrame({'close': np.random.normal(1.10, 0.001, 512)})
start = time.time()
timesfm_bridge.update_risk_cache("TIMING_TEST", test_df)
end = time.time()
print(f"[TIMING] Completed in {end - start:.2f} seconds.")
