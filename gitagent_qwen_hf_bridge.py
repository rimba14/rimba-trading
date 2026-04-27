from openai import OpenAI
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

class QwenLocalBridge:
    """
    Qwen 2.5 Local Bridge via Ollama.
    Provides local LLM intelligence for the Sentinel environment.
    """
    def __init__(self):
        # Local Ollama Configuration (OpenAI-compatible)
        self.client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )
        self.model = "qwen2.5-coder:3b"

    def chat_completion(self, messages: list, temperature: float = 0.7):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                extra_body={"num_thread": 2} # CPU Guardrails
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Qwen Local Error: {e}"

if __name__ == "__main__":
    bridge = QwenLocalBridge()
    test_msg = [{"role": "user", "content": "Write a python function to calculate the 14-period smoothed ATR."}]
    print(f"[TEST] Querying LOCAL {bridge.model}...")
    print(bridge.chat_completion(test_msg))
