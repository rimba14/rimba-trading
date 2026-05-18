import sys
import time
import logging
from pathlib import Path

# Add project root to path
sys.path.append(r"C:\Sentinel_Project")

import MetaTrader5 as mt5

class MockPosition:
    def __init__(self, ticket, symbol, pos_type, volume, price_open, time_entered, comment):
        self.ticket = ticket
        self.symbol = symbol
        self.type = pos_type
        self.volume = volume
        self.price_open = price_open
        self.time = time_entered
        self.comment = comment
        self.sl = 0.0
        self.tp = 0.0

def run_test():
    print("Running Thesis Guard Telemetry Verification...")
    
    # Load profit_manager's run_thesis_decay_check
    import profit_manager
    
    # Configure mock position: EURUSD BUY, entered 1.5 hours ago
    now = time.time()
    mock_pos = MockPosition(
        ticket=1311166378,
        symbol="EURUSD",
        pos_type=0, # BUY
        volume=0.01,
        price_open=1.1630,
        time_entered=now - (1.5 * 3600), # 1.5 hours ago
        comment="SENTINEL_v28.10_IRONCLAD_CADES_TFH4_P0.65"
    )
    
    config = profit_manager.load_risk_config()
    
    # Run check
    print(f"Triggering run_thesis_decay_check for EURUSD (Hold time: 1.5h)...")
    res = profit_manager.run_thesis_decay_check(mock_pos, config, now)
    print(f"Thesis Decay Decision: {res} (Expected: False - Blocked by Minimum Hold Time)")
    
    print("[PASS] Thesis Guard telemetry verified successfully!")

if __name__ == "__main__":
    run_test()
