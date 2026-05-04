import requests
import json
import sys

prompt = """
You are a quantitative trading analyst (Qwen). Please analyze the following post-mortem for a recent EURUSD trade that hit its stop loss.

Trade Details:
- Symbol: EURUSD
- Direction: SELL
- Entry Price: 1.16911
- Virtual Stop Loss Level: 1.16965 (Calculated dynamically via ATR)
- Exit Price: 1.17254 (Price at which the liquidation was executed, indicating potential slippage or a fast gap up)
- Trade Comment: 'v17.2_p0.00' (Indicates it was opened by an older pipeline version, and potentially with 0.00 conviction due to a concept drift forced override or a bug).

Why did this position hit a stop loss, and what are the key takeaways for the Sentinel system?
"""

url = "http://127.0.0.1:11434/api/generate"
payload = {
    "model": "qwen2.5-coder:3b",
    "prompt": prompt,
    "stream": False
}

try:
    response = requests.post(url, json=payload)
    response.raise_for_status()
    result = response.json()
    print(result.get("response", "No response from Qwen."))
except Exception as e:
    print(f"Error querying Qwen via Ollama: {e}")
