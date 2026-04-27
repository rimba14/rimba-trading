import urllib.request
import re
import time

class InsiderAgent:
    def __init__(self, cache_timeout_mins=60):
        self.cache_timeout = cache_timeout_mins * 60
        self.cluster_buys = []
        self.last_fetch_time = 0.0

    def _scrape_openinsider(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        except Exception as e:
            print(f"[INSIDER] Error fetching OpenInsider: {e}")
            return []
            
        raw_matches = re.findall(r'<td><b><a href="/([^"]+)">', html)
        if not raw_matches:
            raw_matches = re.findall(r'<td><a href="/([^"]+)">', html)
            
        tickers = []
        for match in raw_matches:
            if re.match(r'^[A-Z]{1,5}$', match):
                tickers.append(match)
                
        unique_tickers = list(dict.fromkeys(tickers))
        return unique_tickers

    def refresh_data(self):
        """Fetch latest cluster buys if cache is expired."""
        current_time = time.time()
        if (current_time - self.last_fetch_time) > self.cache_timeout or not self.cluster_buys:
            print("[INSIDER] Refreshing OpenInsider Cluster Buys data...")
            self.cluster_buys = self._scrape_openinsider("http://openinsider.com/latest-cluster-buys")
            self.last_fetch_time = current_time

    def get_insider_score(self, sym):
        """
        Returns +15 edge if the ticker is experiencing C-Suite cluster buying.
        Returns 0 otherwise.
        """
        self.refresh_data()
        
        if sym in self.cluster_buys:
            return 15.0
        return 0.0

# Singleton instance for easy importing
_instance = InsiderAgent()

def get_insider_score(sym):
    return _instance.get_insider_score(sym)

if __name__ == "__main__":
    print("Testing InsiderAgent...")
    score = get_insider_score("AAPL")
    print(f"AAPL insider score: {score}")
    
    # Check what is currently hot
    _instance.refresh_data()
    print(f"Current Cluster Buys: {_instance.cluster_buys[:20]}")
