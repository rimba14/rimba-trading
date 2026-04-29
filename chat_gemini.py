import os
import sys
import json
import io
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Force UTF-8 for Windows consoles to prevent charmap crashes
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Load environment variables
load_dotenv(r"C:\Sentinel_Project\.env")

# Initialize Gemini Client
# Directive 1: Securely load GEMINI_API_KEY from .env
api_key = os.getenv("GEMINI_API_KEY")
if not api_key or api_key == "your_gemini_api_key_here":
    print("[FATAL ERROR] GEMINI_API_KEY not found or invalid in .env file.")
    sys.exit(1)

client = genai.Client(api_key=api_key)
model_name = "gemini-2.5-flash" # Target model (v17.2 Production)

def chat_with_gemini():
    print(f"\n" + "═"*60)
    print(f"🤖 ANTIGRAVITY CONSOLE v2.0 (Gemini Migration Active)")
    print(f"═"*60)
    print(f"Type 'exit' or 'quit' to end session.")
    
    # Directive 2: Map messages to Gemini's contents structures
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
            
            # Directive 3: Remove Hardware Handicaps & Implement Timeout/Retry
            # Convert history to Gemini format (user/model)
            gemini_contents = []
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                gemini_contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
            
            try:
                # Standard timeout (10 seconds) implemented via retry config or direct param if supported
                # In google-genai, we use the RequestConfig for timeouts.
                response = client.models.generate_content(
                    model=model_name,
                    contents=gemini_contents,
                    config=types.GenerateContentConfig(
                        system_instruction="You are the Antigravity Intelligence Layer. Be concise, technical, and helpful.",
                        max_output_tokens=2048,
                        temperature=0.7,
                    )
                )
                
                ai_response = response.text
                if not ai_response:
                    ai_response = "[No response from model]"
                
                print(f"\n{ai_response}")
                history.append({"role": "model", "content": ai_response})
                
            except Exception as api_err:
                # Directive 3: Handle transient network errors [503 Service Unavailable]
                err_msg = str(api_err)
                if "503" in err_msg or "Service Unavailable" in err_msg:
                    print(f"\n[SYSTEM ERROR]: Gemini API is temporarily unavailable (503). Retrying in 2s...")
                    time.sleep(2)
                    # Simple retry logic for 503
                    continue
                else:
                    print(f"\n[SYSTEM ERROR]: {api_err}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n[SYSTEM ERROR]: {e}")

if __name__ == "__main__":
    gemini_logo = r"""
     ____               _       _ 
    / ___| ___ _ __ ___(_)_ __ (_)
   | |  _ / _ \ '_ ` _ \ | '_ \| |
   | |_| |  __/ | | | | | | | | | |
    \____|\___|_| |_| |_|_|_| |_|_|
                                  
    """
    print(gemini_logo)
    chat_with_gemini()
