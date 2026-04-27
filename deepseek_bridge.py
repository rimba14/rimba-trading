import os
import requests
import json
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

class DeepSeekBridge:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.base_url = "https://api.groq.com/openai/v1"
        self.model = "llama-3.3-70b-versatile" 

    def chat_completion(self, messages: list, temperature: float = 0.6):
        if not self.api_key:
            return "ERROR: GROQ_API_KEY missing."

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except Exception as e:
            return f"DeepSeek API Error: {e}"

if __name__ == "__main__":
    # Standalone Test
    bridge = DeepSeekBridge()
    test_msg = [{"role": "user", "content": "Briefly explain why a 1.8x ATR stop loss is better than a 1.2x ATR stop in a low-VIX regime."}]
    print("[TEST] Sending prompt to DeepSeek-R1...")
    print(bridge.chat_completion(test_msg))
