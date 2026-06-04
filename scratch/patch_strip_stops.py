file_path = r"C:\Sentinel_Project\fastapi_sniper.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

bad_code = """@app.post("/strip_stops")
async def strip_stops(payload: dict):
    ticket = payload["ticket"]
    mt5.order_modify(ticket, sl=0.0, tp=0.0)
    logger.warning(f"PHYSICAL STOPS STRIPPED: ticket {ticket}")
    return {"status": "stripped", "ticket": ticket}"""

good_code = """@app.post("/strip_stops")
async def strip_stops(payload: dict):
    ticket = payload["ticket"]
    
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return {"status": "error", "message": "Position not found"}
        
    pos = pos[0]
    
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": pos.ticket,
        "sl": 0.0,
        "tp": 0.0,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Failed to strip physical stops on {ticket}: {result.comment}")
    else:
        logger.warning(f"PHYSICAL STOPS STRIPPED: ticket {ticket}")
        
    return {"status": "stripped", "ticket": ticket}"""

if bad_code in content:
    content = content.replace(bad_code, good_code)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched strip_stops endpoint in fastapi_sniper.py.")
