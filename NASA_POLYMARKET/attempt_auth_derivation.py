import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from dotenv import load_dotenv

load_dotenv('C:\\Sentinel_Project\\NASA_POLYMARKET/.env')

def attempt_derivation():
    private_key = os.getenv("POLYGON_PRIVATE_KEY")
    funder = "0xE8294bc036BDc1C22b12D17cc9B4cd97Dd007318"
    base_url = "https://clob.polymarket.com"
    
    client = ClobClient(
        base_url,
        key=private_key,
        chain_id=137,
        signature_type=1,
        funder=funder
    )
    
    print(f"🔐 [AUTH] Attempting to derive API credentials for Signer: {client.get_address()}...")
    try:
        # derive_api_key is often used if they were created via the SDK's derivation path
        creds = client.derive_api_key()
        print("✅ [SUCCESS] Credentials Derived!")
        print(f"API_KEY: {creds.api_key}")
        print(f"API_SECRET: {creds.api_secret}")
        print(f"API_PASSPHRASE: {creds.api_passphrase}")
    except Exception as e:
        print(f"❌ [FAIL] Could not derive credentials: {e}")

if __name__ == "__main__":
    attempt_derivation()
