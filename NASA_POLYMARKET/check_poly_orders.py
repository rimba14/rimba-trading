import os
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv('C:\\Sentinel_Project\\NASA_POLYMARKET/.env')

class PolyDiagnostic:
    def __init__(self):
        self.api_key = os.getenv("POLYMARKET_API_KEY")
        self.api_secret = os.getenv("POLYMARKET_API_SECRET")
        self.api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE")
        self.private_key = os.getenv("POLYGON_PRIVATE_KEY")
        self.funder = "0x0e0502ccE5A641dFC3B61a258C0523DC3Ad70923"
        self.base_url = "https://clob.polymarket.com"

        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds
        from py_clob_client_v2 import SignatureTypeV2
        
        self.client = ClobClient(
            self.base_url,
            key=self.private_key,
            chain_id=137,
            signature_type=SignatureTypeV2.POLY_PROXY,
            funder=self.funder
        )
        self.client.set_api_creds(ApiCreds(self.api_key, self.api_secret, self.api_passphrase))

    def check_account_profile(self):
        print(f"SEARCH Signer Address: {self.client.get_address()}")
        print(f"SEARCH Funder Address: {self.funder}")
        try:
            # Check API connectivity
            status = self.client.get_ok()
            print(f"OK Connectivity Status: {status}")
            
            # Get account orders
            orders = self.client.get_open_orders()
            print(f"OK SUCCESS: Orders Found ({len(orders)} active).")
            print(json.dumps(orders, indent=2))
            
            # Get trades
            print("\nTRADES [TRADES] Checking for recent match history...")
            trades = self.client.get_trades()
            print(json.dumps(trades, indent=2))
            
        except Exception as e:
            print(f"CRITICAL: {e}")

if __name__ == "__main__":
    diag = PolyDiagnostic()
    diag.check_account_profile()
