import yfinance as yf
import json
import os
import pandas as pd
from datetime import datetime

class NewsPerceiver:
    """
    FinGPT-inspired News Perception Layer (Sentinel V2)
    Targets: C:\\Sentinel_Project\\ disk for space efficiency.
    """
    def __init__(self):
        self.output_dir = "C:\\Sentinel_Project\\news_perception/"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        # Institutional Ticker Mapper
        self.mapper = {
            "XAUUSD": "GC=F",
            "XAGUSD": "SI=F",
            "BTCUSD": "BTC-USD",
            "ETHUSD": "ETH-USD",
            "SP500": "^GSPC",
            "NAS100": "^IXIC"
        }

    def get_latest_news_sentiment(self, symbol: str) -> dict:
        search_sym = self.mapper.get(symbol, symbol)
        print(f"[PERCEIVER] Ingesting news for {symbol} (Target: {search_sym})...")
        try:
            ticker = yf.Ticker(search_sym)
            news = ticker.news
            
            if not news:
                return {"symbol": symbol, "pulse": 0.0, "count": 0, "rationale": "No fresh news detected."}
            
            # Simple alpha heuristic: Count positive vs negative keywords
            pos_words = ["bullish", "jump", "record", "gain", "profit", "surge", "buy", "outperform", "rise", "climb"]
            neg_words = ["bearish", "drop", "loss", "crash", "slump", "sell", "underperform", "fall", "dip"]
            
            total_score = 0
            count = 0
            for item in news[:10]: # Top 10 headlines
                # Adjusting for different news dict structures
                content = item.get('content', {})
                title = content.get('title', item.get('title', '')).lower()
                
                if not title: continue
                
                score = 0
                for w in pos_words: 
                    if w in title: score += 1
                for w in neg_words:
                    if w in title: score -= 1
                total_score += score
                count += 1
            
            normalized_pulse = max(-1.0, min(1.0, total_score / (count if count > 0 else 1)))
            
            res = {
                "symbol": symbol,
                "pulse": normalized_pulse,
                "count": count,
                "timestamp": datetime.now().isoformat(),
                "rationale": f"Analyzed {count} headlines for {search_sym}. Net signal: {normalized_pulse}"
            }
            
            self._cache_result(symbol, res)
            return res
            
        except Exception as e:
            return {"symbol": symbol, "pulse": 0.0, "error": str(e)}

    def _cache_result(self, symbol, data):
        path = os.path.join(self.output_dir, f"{symbol}_pulse.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

if __name__ == "__main__":
    import sys
    symbol = sys.argv[sys.argv.index("--symbol") + 1] if "--symbol" in sys.argv else "XAUUSD"
    perceiver = NewsPerceiver()
    result = perceiver.get_latest_news_sentiment(symbol)
    print(json.dumps(result, indent=2))
