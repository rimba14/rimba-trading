import os
import requests
import json
from dotenv import load_dotenv

# Load keys from Drive E
load_dotenv("C:\\Sentinel_Project\\.env")

class GLMChat:
    """
    Instant GLM-5.1 Bridge for Live Interaction.
    """
    def __init__(self):
        self.base_url = "https://open.bigmodel.cn/api/paas/v4" # Official Zhipu v4 endpoint
        self.model = "glm-4" 
        
        provider = str(os.environ.get("GLM_PROVIDER", "")).lower()
        if "openrouter" in provider:
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = "z-ai/glm-4.5-air:free" 
            self.api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ZHIPU_API_KEY")
        elif "huggingface" in provider or os.environ.get("HF_TOKEN"):
            self.api_key = os.environ.get("HF_TOKEN")
            self.model = os.environ.get("HF_GLM_MODEL", "THUDM/glm-4-9b-chat")
            self.base_url = f"https://api-inference.huggingface.co/models/{self.model}/v1"
        else:
            self.api_key = os.environ.get("ZHIPU_API_KEY") or os.environ.get("OPENROUTER_API_KEY")

        # Set up a hardened session
        self.session = requests.Session()
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def chat(self, prompt: str):
        if not self.api_key:
            return "ERROR: Provider-specific API KEY missing in C:\\Sentinel_Project\\.env"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }

        try:
            # Phase 27: Hardened Timeout (Connect: 3.05s, Read: 15s)
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=(3.05, 15)
            )
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except requests.exceptions.Timeout:
            return "GLM API Error: Request timed out. The model might be busy or the connection is slow."
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                return "GLM API Error: Rate limited (429). Please wait a moment before trying again."
            return f"GLM API Error: HTTP {e.response.status_code} - {e.response.text}"
        except Exception as e:
            return f"GLM API Error: {e}"

def main():
    import sys
    chat_bot = GLMChat()
    
    # Handle command-line arguments if provided
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        response = chat_bot.chat(user_input)
        print(f"\nGLM-4.5: {response}\n")
        return

    print(f"--- GLM-5.1 Live Connection ({chat_bot.model}) ---")
    print("Type 'exit' to quit.")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
            
        response = chat_bot.chat(user_input)
        print(f"\nGLM-4.5: {response}\n")

if __name__ == "__main__":
    main()
