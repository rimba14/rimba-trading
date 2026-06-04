import os
import asyncio
import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load configuration from .env
load_dotenv("C:\\Sentinel_Project\\.env")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
REASONING_MODEL = os.getenv("REASONING_MODEL", "qwen2.5-coder:3b")
KEEP_ALIVE = int(os.getenv("OLLAMA_KEEP_ALIVE", "-1"))
TIMEOUT = int(os.getenv("REASONING_TIMEOUT", "30"))
FAILSAFE_CONVICTION = float(os.getenv("CONVICTION_FAILSAFE", "0.500"))

class QwenLocalBridge:
    """
    Qwen 2.5 Local Bridge via Ollama (v17.2 Production Build).
    Implements Memory Lock (keep_alive=-1) and Fail-Safe Conviction logic.
    """
    def __init__(self):
        # Local Ollama Configuration (OpenAI-compatible for basic chat)
        self.client = AsyncOpenAI(
            base_url=f"{OLLAMA_HOST}/v1",
            api_key="ollama"
        )
        self.model = REASONING_MODEL

    async def chat_completion(self, messages: list, temperature: float = 0.7, enable_thinking: bool = True):
        """
        Executes inference with RAM-lock and thinking enabled.
        Fails safe to a neutral conviction if the endpoint times out or errors.
        """
        try:
            # Using OpenAI SDK with extra_body for compliance with v17.2 directive
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                timeout=TIMEOUT,
                extra_body={
                    "keep_alive": KEEP_ALIVE,
                    "enable_thinking": enable_thinking # v17.2 Native Reasoning
                }
            )
            return response.choices[0].message.content
        
        except Exception as e:
            print(f"[REASONING_ERROR] {e} | Forcing Failsafe: {FAILSAFE_CONVICTION}")
            # In a real trading scenario, we'd return a structured JSON with conviction
            return str(FAILSAFE_CONVICTION)

    async def pre_flight_audit(self):
        """
        Phase 5: HTTP Pre-Flight Audit against Ollama tags endpoint.
        """
        try:
            url = f"{OLLAMA_HOST}/api/tags"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5)
                if response.status_code == 200:
                    print(f"[PRE-FLIGHT] Ollama Connectivity: OK")
                    models = [m['name'] for m in response.json().get('models', [])]
                    if self.model in models or f"{self.model}:latest" in models:
                        print(f"[PRE-FLIGHT] Model {self.model}: READY")
                        return True
                    else:
                        print(f"[PRE-FLIGHT] Model {self.model}: NOT FOUND")
                        return False
            return False
        except Exception as e:
            print(f"[PRE-FLIGHT] Audit Failed: {e}")
            return False

async def main():
    bridge = QwenLocalBridge()
    if await bridge.pre_flight_audit():
        test_msg = [{"role": "user", "content": "Analyze trade conviction for AAPL breakout. Return value only."}]
        print(f"[TEST] Querying LOCAL {bridge.model} with RAM Lock...")
        result = await bridge.chat_completion(test_msg)
        print(f"[RESULT] Conviction: {result}")
    else:
        print("[CRITICAL] SRE Halt: Ollama Pre-Flight Audit Failed.")

if __name__ == "__main__":
    asyncio.run(main())
