import os
import time
import json
import requests
from dotenv import load_dotenv
from weather_oracle import WeatherOracle
from NASA_POLYMARKET.execution_logic import PolyExecutionAgent

# Load credentials from the legacy NASA_POLYMARKET path
load_dotenv("C:/Sentinel_Project/NASA_POLYMARKET/.env")

class WeatherTradingDaemon:
    def __init__(self):
        self.oracle = WeatherOracle()
        self.executor = PolyExecutionAgent()
        self.target_market_query = "Will it rain in London"
        self.current_state = "MONITORING_NO"
        self.yes_token = "23786009861607578610475312618266374029318959786171125842374617965138445997993"
        self.no_token = "62530727860581457834398358673645663391163983593057696005239032071194110663396"
        self.amount_usd = 5.0 # Polymarket enforces a 5-token minimum size constraint
        
    def discover_target_market(self):
        """Discovers the NYC rain market IDs."""
        url = f"https://gamma-api.polymarket.com/public-search?q={self.target_market_query}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                markets = resp.json().get('markets', [])
                for m in markets:
                    # Look for active NYC rain market
                    if m.get('active') and not m.get('closed') and "London" in m.get('question'):
                        tokens = m.get('clobTokenIds', [])
                        if len(tokens) >= 2:
                            self.yes_token = tokens[0]
                            self.no_token = tokens[1]
                            print(f"✅ [DAEMON] Market Discovered: {m.get('question')}")
                            return True
            return False
        except Exception as e:
            print(f"❌ [DAEMON] Discovery Error: {e}")
            return False

    def run(self):
        print("LAUNCH [DAEMON] Polymarket Weather Trading Node LIVE.")
        print(f"LOCATION Target: {self.target_market_query} (London)")
        
        while True:
            try:
                if self.current_state == "SCANNING":
                    print(f"MARKET [DAEMON] Using explicit London Precipitation Market. Establishing initial NO position for ${self.amount_usd}...")
                    self.executor.place_order(
                        token_id=self.no_token,
                        side="BUY",
                        amount_usd=self.amount_usd,
                        limit_price=0.99 # Taking the offer if it exists or placing a high-priority limit
                    )
                    self.current_state = "MONITORING_NO"

                # Monitoring Phase
                if self.current_state == "MONITORING_NO":
                    res = self.oracle.check_agreement(threshold=30)
                    print(f"WEATHER [ORACLE] Agreement: {res['agreement']} | Consensus: {[s['condition'] for s in res['sources']]}")
                    
                    if res["agreement"]:
                        print("FLIP [FLIP] 3/3 API Consensus reached! Flipping to YES!")
                        # 1. Cancel existing NO orders
                        self.executor.cancel_all_orders()
                        # 2. Buy YES
                        self.executor.place_order(
                            token_id=self.yes_token,
                            side="BUY",
                            amount_usd=self.amount_usd,
                            limit_price=0.99
                        )
                        self.current_state = "MONITORING_YES"
                
                time.sleep(60) # Poll every minute

            except Exception as e:
                print(f"❌ [DAEMON] Runtime Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    daemon = WeatherTradingDaemon()
    daemon.run()
