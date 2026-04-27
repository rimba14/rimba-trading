"""
model_factory.py - UNIFIED AI INTERFACE
Allows swapping LLMs for different agents without changing agent code.
"""

import os
import openai
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv("C:\\Sentinel_Project\\.env")

class ModelFactory:
    """Unified LLM interface."""
    
    MODELS = {
        "claude": "claude-3-5-sonnet-20240620", # Updated to latest standard
        "gpt4": "gpt-4o",
        "deepseek": "deepseek-chat",
        "groq": "llama-3.3-70b-versatile",
        "qwen": "qwen2.5-coder:3b"
    }
    
    @staticmethod
    def call(model: str, system: str, user: str, max_tokens: int = 1000) -> str:
        """Centralized call method for all supported models."""
        
        if model == "qwen":
            # Local TurboQuant Endpoint (Antigravity Integration)
            client = openai.OpenAI(
                base_url="http://127.0.0.1:8080/v1",
                api_key="EMPTY",
                timeout=900.0
            )
            try:
                resp = client.chat.completions.create(
                    model=ModelFactory.MODELS["qwen"],
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.1,
                    extra_body={"num_thread": 4}
                )
                return resp.choices[0].message.content
            except Exception as e:
                return f"Local Qwen Error: {e}"

        elif model == "claude":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key: return "ERROR: ANTHROPIC_API_KEY missing."
            client = Anthropic(api_key=api_key)
            try:
                msg = client.messages.create(
                    model=ModelFactory.MODELS["claude"],
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}]
                )
                return msg.content[0].text
            except Exception as e:
                return f"Claude Error: {e}"
        
        elif model in ("gpt4", "deepseek", "groq"):
            # Setup endpoints and keys
            endpoints = {
                "gpt4": ("https://api.openai.com/v1", os.getenv("OPENAI_API_KEY")),
                "deepseek": ("https://api.deepseek.com/v1", os.getenv("DEEPSEEK_API_KEY")),
                "groq": ("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY")),
            }
            
            base_url, api_key = endpoints.get(model, (None, None))
            if not api_key:
                return f"ERROR: {model.upper()}_API_KEY missing."
            
            client = openai.OpenAI(base_url=base_url, api_key=api_key)
            try:
                resp = client.chat.completions.create(
                    model=ModelFactory.MODELS[model],
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.1
                )
                return resp.choices[0].message.content
            except Exception as e:
                return f"{model.upper()} Error: {e}"
                
        return f"ERROR: Model {model} not supported."
