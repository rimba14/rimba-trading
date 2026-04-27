import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

class SocialOracle:
    """
    Sentinel Social Intelligence Layer (FinTwitBERT Bridge)
    Targets: C:\\Sentinel_Project\\ disk.
    """
    def __init__(self):
        self.api_key = os.getenv("HUGGING_FACE_TOKEN")
        # Fallback to standard FinBERT for test
        self.model_id = "ProsusAI/finbert"
        self.api_url = f"https://api-inference.huggingface.co/models/{self.model_id}"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    def get_social_score(self, text: str) -> float:
        if not self.api_key:
            return 0.0 # Silent fail if no token
        
        try:
            response = requests.post(self.api_url, headers=self.headers, json={"inputs": text})
            result = response.json()
            print(f"[SOCIAL-DEBUG] RAW: {result}")
            
            # If model is loading, it returns {'error': 'Model ... is currently loading', 'estimated_time': ...}
            if isinstance(result, dict) and "error" in result:
                print(f"[SOCIAL-ORACLE] HF Error: {result['error']}")
                return 0.0

            # FinTwitBERT labels: Bearish, Neutral, Bullish
            if isinstance(result, list) and len(result) > 0:
                labels = result[0] # List of dicts
                top_label = max(labels, key=lambda x: x['score'])
                
                print(f"[SOCIAL-ORACLE] Top Signal: {top_label['label']} ({top_label['score']:.4f})")
                
                mapping = {
                    "BEARISH": -1.0,
                    "NEUTRAL": 0.0,
                    "BULLISH": 1.0,
                    "LABEL_0": -1.0, # Alternative mapping for BERT-base
                    "LABEL_1": 0.0,
                    "LABEL_2": 1.0
                }
                return mapping.get(top_label['label'].upper(), 0.0)
            
            # Phase 211 B: Heuristic Fallback (Resilience layer)
            return self._heuristic_fallback(text)
        except Exception as e:
            print(f"[SOCIAL-ORACLE] Error: {str(e)}")
            return self._heuristic_fallback(text)

    def _heuristic_fallback(self, text: str) -> float:
        """
        Keyword-based sentiment backup for restricted environments.
        """
        t = text.lower()
        pos_words = ["bullish", "long", "moon", "buy", "up", "breakout", "strong"]
        neg_words = ["bearish", "short", "dump", "sell", "down", "crash", "weak"]
        
        score = 0.0
        for w in pos_words: 
            if w in t: score += 1
        for w in neg_words:
            if w in t: score -= 1
            
        return max(-1.0, min(1.0, score / 2.0))

if __name__ == "__main__":
    oracle = SocialOracle()
    test_text = "Gold is looking super strong here, breakout confirmed! 🚀"
    score = oracle.get_social_score(test_text)
    print(f"Test Score: {score}")
