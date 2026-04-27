import os
from eth_account import Account
from web3 import Web3
from dotenv import load_dotenv

load_dotenv('C:\\Sentinel_Project\\NASA_POLYMARKET/.env')

RPC_URL = os.getenv("POLYGON_RPC_URL")
PROXY_ADDRESS = "0x0e0502cce5a641dfc3b61a258c0523dc3ad70923"

def check_owner():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("❌ RPC connection failed")
        return

    # Try common owner/signer functions
    abi = [
        {"inputs": [], "name": "owner", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getOwner", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "signer", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"}
    ]
    
    contract = w3.eth.contract(address=w3.to_checksum_address(PROXY_ADDRESS), abi=abi)
    
    print(f"🔍 Probing owner for {PROXY_ADDRESS}...")
    for func_name in ["owner", "getOwner", "signer"]:
        try:
            res = getattr(contract.functions, func_name)().call()
            print(f"✅ {func_name}(): {res}")
        except Exception as e:
            print(f"❌ {func_name}(): Failed")

if __name__ == "__main__":
    check_owner()
