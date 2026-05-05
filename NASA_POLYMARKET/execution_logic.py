import os
import time
from dotenv import load_dotenv
from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import ApiCreds, OrderArgs
from py_clob_client_v2 import SignatureTypeV2, Side, OrderType

load_dotenv()

class PolyExecutionAgent:
    """
    Handles secure order execution on Polymarket CLOB using the official SDK.
    """
    def __init__(self):
        self.api_key = os.getenv("POLYMARKET_API_KEY")
        self.api_secret = os.getenv("POLYMARKET_API_SECRET")
        self.api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE")
        self.private_key = os.getenv("POLYGON_PRIVATE_KEY")
        self.base_url = "https://clob.polymarket.com"
        
        if self.private_key:
            # Initialize the official Polymarket CLOB Client for Proxy wallets
            self.client = ClobClient(
                self.base_url,
                key=self.private_key,
                chain_id=137,
                signature_type=SignatureTypeV2.POLY_PROXY, 
                funder="0x0e0502ccE5A641dFC3B61a258C0523DC3Ad70923"
            )


            
            # Set Level 2 Credentials for Trading
            creds = ApiCreds(
                api_key=self.api_key,
                api_secret=self.api_secret,
                api_passphrase=self.api_passphrase
            )
            self.client.set_api_creds(creds)
            print(f"LOCK [EXECUTION] SDK Client Initialized for Signer: {self.client.get_address()}")
        else:
            self.client = None
            print("WARNING [EXECUTION] No Private Key found. Operations restricted to SIMULATION.")

    def place_order(self, token_id: str, side: str, amount_usd: float, limit_price: float):
        """Places a signed limit order via the SDK."""
        if not self.client:
            print(f"SIMULATION [SIMULATION] {side} {amount_usd}USD of {token_id} @ {limit_price}")
            return None
            
        size = round(amount_usd / limit_price, 2)
        
        print(f"ORDER [EXECUTION] Submitting {side} for {token_id[:10]}... (Size: {size})")
        
        try:
            # V2 unified create and post order
            side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL
            
            order_args = OrderArgs(
                price=limit_price,
                size=size,
                side=side_enum,
                token_id=token_id
            )
            
            print(f"POST [POSTING] Broadcasting signed order to V2 exchange...")
            resp = self.client.create_and_post_order(
                order_args=order_args,
                order_type=OrderType.GTC
            )
            
            print(f"DEBUG [DEBUG] API Response: {resp}")
            
            if resp and resp.get("success"):
                print(f"SUCCESS [SUCCESS] Order Accepted | OrderID: {resp.get('orderID')}")
                return resp
            else:
                print(f"ERROR [API_ERR] Order rejected: {resp}")
                return None
                
        except Exception as e:
            print(f"CRITICAL [CRITICAL] SDK Exception during execution: {e}")
            return None

    def cancel_all_orders(self):
        """Cancels all open orders for the account."""
        if not self.client:
            print("SIMULATION [SIMULATION] Cancelling all orders...")
            return True
            
        print("CANCEL [CANCEL] Sending cancel_all request...")
        try:
            resp = self.client.cancel_all()
            print(f"SUCCESS [SUCCESS] Cancel Response: {resp}")
            return resp
        except Exception as e:
            print(f"CRITICAL [CRITICAL] SDK Exception during cancellation: {e}")
            return None

if __name__ == "__main__":

    agent = PolyExecutionAgent()
    # Test with a dummy order
    # agent.place_order("113409880230292298233407295132840039308407512477092152217529840507076789827749", "BUY", 10.0, 0.21)
