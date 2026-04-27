import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

class GroqCoder:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "qwen/qwen3-32b" # Optimized for coding & instruction following as of April 2026

    def generate_code(self, prompt: str):
        if not self.api_key:
            return "ERROR: GROQ_API_KEY missing from .env."

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        system_msg = "You are an expert Python Engineer specialized in the MetaTrader5 (MT5) and Vantage Trading frameworks. Provide clean, production-ready, risk-locked code."
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1 # Low temp for precise coding
        }

        try:
            res = requests.post(self.url, headers=headers, json=payload, timeout=30)
            res.raise_for_status()
            return res.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Coding Assistant Error: {e}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python C:\\Sentinel_Project\\code.py \"Your coding task...\"")
    else:
        coder = GroqCoder()
        print("\n[VANTAGE CODER]: Thinking...")
        print(coder.generate_code(" ".join(sys.argv[1:])))
