import os
import argparse
import MetaTrader5 as mt5
import deepseek_bridge
import git_arctic
import psutil
from datetime import datetime

def get_trading_context():
    """Gathers live context from the Vantage engine state."""
    context = ""
    watchlist = ["EURUSD", "GBPUSD", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD", "SP500", "GER40"]
    
    # 1. MT5 Account/Position Summary
    if mt5.initialize():
        acc = mt5.account_info()
        pos = mt5.positions_get()
        if acc:
            context += f"ACCOUNT: Equity ${acc.equity:.2f}, Balance ${acc.balance:.2f}, Margin Level {acc.margin_level:.1f}%\n"
        if pos:
            context += f"POSITIONS: {len(pos)} active: {[p.symbol for p in pos]}\n"
        mt5.shutdown()

    # 2. Process Health Check
    python_procs = [p.info['name'] for p in psutil.process_iter(['name'])]
    context += f"\nPROCESSES: Python instances active: {python_procs.count('python.exe')}\n"

    # 3. Direct AI Signal Audit (ArcticDB)
    context += "\nLIVE AI SIGNALS (ArcticDB):\n"
    try:
        store = git_arctic.get_arctic()
        lib = store['oracle_cache']
        for sym in watchlist:
            try:
                # Get HMM
                h_item = lib.read(f"{sym}_hmm")
                h_data = h_item.data.to_dict('records')[-1]
                
                # Get Kronos
                k_item = lib.read(f"{sym}_kronos")
                k_data = k_item.data.to_dict('records')[-1]
                
                age = int(datetime.now().timestamp() - k_data['timestamp'])
                context += f"[{sym}] Regime: {h_data['state']}, AI_Prob: {k_data['kronos_prob']:.3f}, Age: {age}s\n"
            except:
                context += f"[{sym}] SIGNAL MISSING OR STALE\n"
    except Exception as e:
        context += f"ARCTIC_DB_ERR: {e}\n"

    return context

def main():
    parser = argparse.ArgumentParser(description="DeepSeek Trading Co-Pilot")
    parser.add_argument("query", type=str, nargs='?', help="Your question for DeepSeek")
    args = parser.parse_args()

    # If no query, enter interactive mode
    bridge = deepseek_bridge.DeepSeekBridge()
    
    print("\n" + "="*60)
    print("DEEPSEEK TRADING CO-PILOT v1.0")
    print("="*60)
    
    context = get_trading_context()
    
    if args.query:
        user_input = args.query
    else:
        user_input = input("\n[USER]: ")

    system_prompt = f"""
    You are the 'Sentinel Strategic Advisor'. You are linked to a LIVE algorithmic trading engine (Vantage).
    
    CURRENT ENGINE CONTEXT:
    {context}
    
    TASK: Use your deep reasoning to answer the user's question about their trading strategy, risk management, or specific positions.
    Be concise but utilize your Chain-of-Thought to identify subtle risks or opportunities.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    print("\n[DEEPSEEK]: (Thinking...)")
    response = bridge.chat_completion(messages)
    print(f"\n{response}\n")

if __name__ == "__main__":
    main()
