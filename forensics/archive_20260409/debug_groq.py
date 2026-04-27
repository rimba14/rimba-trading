import requests
import os
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

api_key = os.environ.get("GROQ_API_KEY")
url = "https://api.groq.com/openai/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "deepseek-r1-distill-llama-70b",
    "messages": [
        {"role": "user", "content": "hello"}
    ]
}

print(f"Testing Groq with {payload['model']}...")
response = requests.post(url, headers=headers, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

if response.status_code != 200:
    print("\nListing available models...")
    models_res = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"})
    print(models_res.text)
