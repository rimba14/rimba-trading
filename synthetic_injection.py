import os
import sys
import time
import requests
import MetaTrader5 as mt5

# Set path
sys.path.append(r"C:\Sentinel_Project")
from fastapi_sniper import execute_exit

def run_synthetic_injection():
    print("=== STARTING LEVEL 76 SRE: SYNTHETIC ALPHA INJECTION ===")
    
    if not mt5.initialize():
        print("[FAIL] MT5 failed to initialize.")
        return
        
    symbol = "USDCHF"
    print(f"Targeting symbol: {symbol}")
    
    # 1. Construct perfectly compliant JSON payload
    payload = {
        "symbol": symbol,
        "direction": "BUY",
        "conviction": 0.95,
        "xgb_p": 0.95,
        "ddqn_p": 0.95,
        "hmm_state": "TREND",
        "timestamp": int(time.time()),
        "reasoning": "SRE Synthetic Plumbing Test",
        "vpin": 0.1,
        "signal_type": "MOMENTUM",
        "rsi": 40.0,
        "alpha_features": {"ATR": 0.01, "order_flow_entropy": 0.2}
    }
    
    print(f"Sending payload to execute_trade endpoint: {payload}")
    
    # 2. Fire request
    try:
        resp = requests.post("http://localhost:8000/execute_trade", json=payload, timeout=10.0)
        print(f"FastAPI Sniper Response Code: {resp.status_code}")
        print(f"FastAPI Sniper Response Body: {resp.text}")
    except Exception as e:
        print(f"[FAIL] Could not contact execute_trade endpoint: {e}")
        mt5.shutdown()
        return

    # 3. Query MT5 to verify trade successfully opened
    print("Verifying open positions in MT5...")
    time.sleep(1.0)
    
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        print("[FAIL] No open position found for USDCHF!")
        mt5.shutdown()
        return
        
    for pos in positions:
        print("\n=== SYNTHETIC POSITION OPENED ===")
        print(f"Ticket: {pos.ticket}")
        print(f"Symbol: {pos.symbol}")
        print(f"Volume: {pos.volume}")
        print(f"Price Open: {pos.price_open}")
        print(f"Stop Loss: {pos.sl}")
        print(f"Take Profit: {pos.tp}")
        print(f"Comment: {pos.comment}")
        
    # 4. Wait 5 seconds
    print("\nHolding position for 5 seconds for visual plumbing verification...")
    time.sleep(5.0)
    
    # 5. Auto-Cleanup: close the trade
    print("\nExecuting Auto-Cleanup exit...")
    for pos in positions:
        success = execute_exit(pos.ticket, pos.symbol, "SYNTH_CLEANUP")
        if success:
            print(f"[OK] Position #{pos.ticket} successfully closed.")
        else:
            print(f"[FAIL] Failed to close position #{pos.ticket}!")
            
    mt5.shutdown()
    print("\n=== SYNTHETIC INJECTION COMPLETED ===")

if __name__ == "__main__":
    run_synthetic_injection()
