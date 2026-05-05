import os
import json
from dotenv import load_dotenv
from py_clob_client_v2 import Side, OrderType
from py_clob_client_v2.clob_types import OrderArgs

# Set PYTHONPATH to include C:/Sentinel_Project
import sys
sys.path.append("C:/Sentinel_Project")

from NASA_POLYMARKET.execution_logic import PolyExecutionAgent

load_dotenv("C:/Sentinel_Project/NASA_POLYMARKET/.env")

def test_order():
    executor = PolyExecutionAgent()
    # Explicit London Precipitation (30mm+) NO Token
    no_token = "62530727860581457834398358673645663391163983593057696005239032071194110663396"
    amount_usd = 5.0 # Min 5 tokens
    limit_price = 0.99
    
    print(f"DEBUG Placing V2 order for {no_token} at ${amount_usd}...")
    resp = executor.place_order(
        token_id=no_token,
        side="BUY",
        amount_usd=amount_usd,
        limit_price=limit_price
    )
    print("DEBUG Response:")
    print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    test_order()
