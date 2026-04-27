import requests
import json
import logging
from typing import List, Dict, Any

class SemanticMemory:
    """
    Sentinel Semantic Memory Palace.
    Bridges to Claude-Mem worker service (Port 37777) for Chroma Vector retrieval.
    """
    def __init__(self, host="http://localhost", port=37777):
        self.endpoint = f"{host}:{port}/api"
        self.timeout = 2.0 # Fast fail for trading loops

    def search_observations(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Implementation of the 3-layer workflow: search -> get_observations.
        """
        try:
            # Step 1: Semantic Search via Chroma
            response = requests.post(
                f"{self.endpoint}/search",
                json={"query": query, "limit": limit},
                timeout=self.timeout
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            
            if not results:
                return []
                
            # Step 2: Fetch full details for relevant IDs
            obs_ids = [r['id'] for r in results]
            details = requests.post(
                f"{self.endpoint}/get_observations",
                json={"ids": obs_ids},
                timeout=self.timeout
            )
            return details.json().get("observations", [])
            
        except Exception as e:
            # Graceful degradation for trading engine
            logging.debug(f"[MEMORY-BRIDGE] Service offline: {e}")
            return []

    def log_observation(self, symbol: str, context: str, outcome: str):
        """Asynchronously logs a market observation for future semantic recall"""
        try:
            payload = {
                "type": "trading_insight",
                "project": "Vantage-13D",
                "content": f"Symbol: {symbol} | Context: {context} | Outcome: {outcome}"
            }
            requests.post(f"{self.endpoint}/observe", json=payload, timeout=0.1)
        except:
            pass

if __name__ == "__main__":
    mem = SemanticMemory()
    print("[TEST] Searching for gold volatility memories...")
    insights = mem.search_observations("gold volatility spikes")
    print(f"Retrieved {len(insights)} semantic insights.")
