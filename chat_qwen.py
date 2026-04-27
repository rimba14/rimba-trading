import os
import sys
import json
import io
from openai import OpenAI
from dotenv import load_dotenv

# Force UTF-8 for Windows consoles to prevent charmap crashes
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Directive 1: Implement the Startup Toggle
print("\n" + "═"*60)
print("SELECT LLM ENGINE (Antigravity Routing):")
print("[1] Local Qwen 2.5B (Free - CPU Guardrails Active)")
print("[2] Cloud LLM (Paid - High Compute via OpenRouter)")
print("═"*60)
choice = input("Enter choice (1/2): ")

# Load environment variables
load_dotenv(r"C:\Sentinel_Project\.env")

# Directive 2: Dynamic Client Initialization
if choice == '1':
    # Local TurboQuant Configuration (Optimized for dual-core CPU)
    client = OpenAI(
        base_url="http://127.0.0.1:8080/v1",
        api_key="EMPTY",
        timeout=900.0
    )
    model_name = "qwen2.5-coder:3b"
    print(f"\n[SYSTEM] Routing to LOCAL TurboQuant ({model_name})...")
else:
    # Cloud OpenRouter Configuration
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        timeout=900.0
    )
    model_name = "google/gemini-2.0-flash-001"
    print(f"\n[SYSTEM] Routing to CLOUD OpenRouter ({model_name})...")

def chat_with_qwen():
    print(f"\n" + "═"*60)
    print(f"🤖 ANTIGRAVITY CONSOLE v1.5 (Dynamic Routing Active)")
    print(f"═"*60)
    print(f"Type 'exit' or 'quit' to end session.")
    
    history = []
    
    while True:
        try:
            user_input = input("\n[USER]: ")
            if user_input.lower() in ['exit', 'quit']:
                print("\nGracefully terminating session...")
                break
            
            history.append({"role": "user", "content": user_input})
            
            # Limit history to prevent context overflow
            if len(history) > 20:
                history = history[-20:]
            
            print(f"\n[{model_name.upper()}]: (Processing request...)")
            
            # Directive 3: Conditional CPU Guardrails (CRITICAL)
            # Ollama specific params only for choice 1
            payload_kwargs = {
                "model": model_name,
                "messages": history
            }
            
            if choice == '1':
                payload_kwargs["extra_body"] = {"num_thread": 2}
            
            response = client.chat.completions.create(**payload_kwargs)
            
            ai_response = response.choices[0].message.content
            print(f"\n{ai_response}")
            history.append({"role": "assistant", "content": ai_response})
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n[SYSTEM ERROR]: {e}")

if __name__ == "__main__":
    qwen_logo = r"""
     ____                      
    / __ \__      _____ _ __  
   | |  | \ \ /\ / / _ \ '_ \ 
   | |__| |\ V  V /  __/ | | |
    \___\_\ \_/\_/ \___|_| |_|
                              
    """
    print(qwen_logo)
    chat_with_qwen()
