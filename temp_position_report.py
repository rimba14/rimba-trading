import os
import requests
import json
import MetaTrader5 as mt5
from chat_glm import GLMChat

def get_full_context():
    if not mt5.initialize():
        return "MT5 Initialization Failed"
    
    positions = mt5.positions_get()
    if not positions:
        mt5.shutdown()
        return "No open positions found."

    open_tickets = [str(p.ticket) for p in positions]
    symbols = list(set([p.symbol for p in positions] + ['EURUSD', 'USDJPY', 'XAUUSD', 'NAS100', 'BTCUSD']))
    
    market_data = {}
    for s in symbols:
        tick = mt5.symbol_info_tick(s)
        if tick:
            market_data[s] = {
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": round((tick.ask - tick.bid), 5)
            }
            
    thesis = {}
    try:
        if os.path.exists("C:\\Sentinel_Project\\position_thesis.json"):
            with open("C:\\Sentinel_Project\\position_thesis.json", "r") as f:
                raw_thesis = json.load(f)
                thesis = {k: v for k, v in raw_thesis.items() if k in open_tickets}
    except Exception as e:
        print(f"Thesis load error: {e}")
    
    report_data = []
    for p in positions:
        ticket_str = str(p.ticket)
        info = {
            "symbol": p.symbol,
            "type": "BUY" if p.type == 0 else "SELL",
            "profit": round(p.profit, 2),
            "price_open": p.price_open,
            "current_price": market_data.get(p.symbol, {}).get("bid" if p.type==0 else "ask", "N/A"),
            "thesis": thesis.get(ticket_str, "Technical thesis pending.")
        }
        report_data.append(info)
        
    mt5.shutdown()
    return json.dumps({"positions": report_data, "market_context": market_data}, indent=2)

def main():
    print("[SYSTEM] Fetching full context (Positions + Market)...")
    context = get_full_context()
    
    prompt = f"System Context: Below is the current list of trading positions, their entry thesis, and overall market levels.\n\n{context}\n\nUser Question: lets look at our current positions and the market. give me an update on our portfolio status, risk, and what is happening in the market."
    
    chat_bot = GLMChat()
    print("[SYSTEM] Calling GLM-4.5...")
    response = chat_bot.chat(prompt)
    print(f"\nGLM-4.5 UpdatC:\\Sentinel_Project\\n{response}")

if __name__ == "__main__":
    main()
