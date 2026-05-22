from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from weather_oracle import WeatherOracle
import uvicorn
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

oracle = WeatherOracle()

# Mock State for Trading
trading_state = {
    "current_bet": "NO",
    "last_trade": "None",
    "pnl": 0.0,
    "agreement": False
}

@app.get("/api/weather")
def get_weather():
    res = oracle.check_agreement(threshold=30)
    
    # Update Trading State
    if res["agreement"] and trading_state["current_bet"] == "NO":
        trading_state["current_bet"] = "YES"
        trading_state["last_trade"] = f"FLIP TO YES at {time.strftime('%H:%M:%S')}"
    elif not res["agreement"] and trading_state["current_bet"] == "YES":
        trading_state["current_bet"] = "NO"
        trading_state["last_trade"] = f"FLIP TO NO at {time.strftime('%H:%M:%S')}"
        
    return {**res, "trading_state": trading_state}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
