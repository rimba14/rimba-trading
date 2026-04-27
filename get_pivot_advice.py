import deepseek_bridge
import os

def run_pivot_audit():
    bridge = deepseek_bridge.DeepSeekBridge()
    
    # Live context from logs/portfolios would be here normally, 
    # but the bridge already handles it if we reuse its logic.
    # To be safe, I'll provide a direct prompt.
    prompt = """
    We are at 26% drawdown ($760 peak to $560 current). 
    We just found 'Precision Friction' (rounding errors causing stop-loss move spam).
    We are currently 142% Risk Saturated.
    Provide the 3 SIMPLEST CHANGES to pivot back to profit. 
    Explain WHY (cause) and HOW (simple implementation).
    """

    messages = [{"role": "user", "content": prompt}]
    print("[*] Consulting Llama-3.3-70B for Profit Roadmap...")
    response = bridge.chat_completion(messages)
    
    with open("C:\\Sentinel_Project\\pivot_roadmap.txt", "w") as f:
        f.write(response)
    print("[*] DONE. Results saved to C:\\Sentinel_Project\\pivot_roadmap.txt")

if __name__ == "__main__":
    run_pivot_audit()
