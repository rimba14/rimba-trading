import os
from dotenv import load_dotenv
import requests
import json

# Load .env
load_dotenv()

def test_gemini(model="gemini-2.0-flash-lite"):
    # Codebase uses GOOGLE_API_KEY, which is mapped from GEMINI_API_KEY
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "FAIL: No API KEY found in .env"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": "Hello. Reply with 'GEMINI_OK'"}]}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            return f"SUCCESS ({model})"
        else:
            return f"FAIL ({model}): {response.status_code} - {response.text}"
    except Exception as e:
        return f"ERROR ({model}): {e}"

def test_groq():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "FAIL: No GROQ_API_KEY"
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": "Hello. Reply with 'GROQ_OK'"}],
        "max_tokens": 10
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            return "SUCCESS (Groq)"
        else:
            return f"FAIL (Groq): {response.status_code} - {response.text}"
    except Exception as e:
        return f"ERROR (Groq): {e}"

if __name__ == "__main__":
    print("=== DUAL-ENGINE API AUDIT (v3) ===")
    print(f"Gemini (2.0-flash-lite): {test_gemini('gemini-2.0-flash-lite')}")
    print(f"Groq:                    {test_groq()}")
