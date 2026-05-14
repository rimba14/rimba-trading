
import os
from dotenv import load_dotenv

def test_env():
    load_dotenv()
    
    required_vars = [
        "HYPER_LIQUID_KEY",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "DISCORD_BOT_TOKEN",
        "DATABASE_URL",
        "SERVER_PORT",
        "API_KEY",
        "GROQ_MODEL",
        "GEMINI_MODEL"
    ]
    
    print("--- Sentinel Environment Variable Audit ---")
    all_present = True
    for var in required_vars:
        val = os.getenv(var)
        if val:
            # Mask sensitive info
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else str(val)
            print(f"[OK] {var}: {masked}")
        else:
            print(f"[FAIL] {var}: NOT FOUND")
            all_present = False
            
    if all_present:
        print("\n[SUCCESS] All essential environment variables are loaded.")
    else:
        print("\n[WARNING] Some environment variables are missing.")

if __name__ == "__main__":
    test_env()
