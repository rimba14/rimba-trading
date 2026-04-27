import os
from execution_logic import PolyExecutionAgent
from dotenv import load_dotenv

load_dotenv('C:\\Sentinel_Project\\NASA_POLYMARKET/.env')

def test_live_order():
    agent = PolyExecutionAgent()
    # NYC Rain (April 2026) - NO Token
    NO_TOKEN = "113409880230292298233407295132840039308407512477092152217529840507076789827749"
    
    print("\n📦 [TEST] Attempting to place a small live order (0.10c limit) to verify auth...")
    # Using a very low price (0.01) to ensure it's a safe limit order that likely won't even fill
    resp = agent.place_order(
        token_id=NO_TOKEN,
        side="BUY",
        amount_usd=2.0,
        limit_price=0.01
    )


    
    if resp and resp.get("success"):
        print("🚀 [SUCCESS] Live order submitted and visible on CLOB!")
    else:
        print(f"❌ [FAILED] Order rejected: {resp}")

if __name__ == "__main__":
    test_live_order()
