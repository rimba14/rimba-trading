import sys
import os
sys.path.append(r"C:\Sentinel_Project")
from qwen_reasoning_engine import QwenReasoningEngine
import json
import logging
logging.basicConfig(level=logging.INFO)

engine = QwenReasoningEngine()
sys_prompt = "You are the Sentinel Meta-Model."
user_prompt = "SYMBOL: BTCUSD | FEATURES: {'W_rsi': 65, 'W_macd': 0.5} | PRIMARY: 1"

print("Starting inference...")
try:
    result = engine.json_with_retry(sys_prompt, user_prompt)
    print(f"Result: {json.dumps(result, indent=2)}")
except Exception as e:
    print(f"ERROR: {e}")
