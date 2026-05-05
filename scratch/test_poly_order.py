import os
import json
from dotenv import load_dotenv
from NASA_POLYMARKET.execution_logic import PolyExecutionAgent

load_dotenv("C:/Sentinel_Project/NASA_POLYMARKET/.env")

def test_order(sig_type=1):
    executor = PolyExecutionAgent()
    # Force the signature type for testing
    executor.client.signature_type = sig_type
    # Explicit London Precipitation (30mm+) NO Token
    no_token = "62530727860581457834398358673645663391163983593057696005239032071194110663396"
    amount_usd = 5.0 # Min 5 tokens
    limit_price = 0.99
    
    print(f"DEBUG Placing order for {no_token} at ${amount_usd}...")
    resp = executor.place_order(
        token_id=no_token,
        side="BUY",
        amount_usd=amount_usd,
        limit_price=limit_price
    )
    print("DEBUG Response:")
    print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    print("--- Testing Signature Type 0 (EOA) ---")
    test_order(sig_type=0)
    print("\n--- Testing Signature Type 1 (Proxy) ---")
    test_order(sig_type=1)
    print("\n--- Testing Signature Type 2 (Gnosis) ---")
    test_order(sig_type=2)
