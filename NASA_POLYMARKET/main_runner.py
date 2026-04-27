import os
import pandas as pd
from nasa_adapter import NasaFireAdapter
from geo_boundary_mapper import GeoBoundaryMapper
from execution_logic import PolyExecutionAgent
from dotenv import load_dotenv

load_dotenv()

from weather_strategy import WeatherStrategyAgent
from mexico_strategy import MexicoWeatherStrategy

def run_satellite_oracle():
    print("\n🛰️  [NASA FIRE] Starting Satellite Anomaly Scan...")
    nasa_sensor = NasaFireAdapter()
    geo_mapper = GeoBoundaryMapper()
    executor = PolyExecutionAgent()
    
    nasa_key = os.getenv("NASA_FIRMS_KEY")
    if not nasa_key or "your_key" in nasa_key:
        data = pd.DataFrame([{'latitude': 40.5, 'longitude': -124.0, 'brightness': 420.0, 'type': 'VIIRS'}])
    else:
        data = nasa_sensor.get_latest_usa_fires()
        if data.empty: return

    activations = geo_mapper.detect_activations(data)
    for region, stat in activations.items():
        if stat['count'] >= 2:
            min_fire_amt = 5.0 * 0.25
            executor.place_order(token_id=f"POLY_FIRE_{region}", side="BUY", amount_usd=max(0.01, min_fire_amt), limit_price=0.25)

def run_weather_oracle():
    print("\n🌩️  [WEATHER ORACLE] Auditing Atmospheric Consensus...")
    YES_TOKEN = "63854199991307994435887259253488274719266100529819197904875322473456385205847"
    NO_TOKEN  = "113409880230292298233407295132840039308407512477092152217529840507076789827749"
    
    nyc_strat = WeatherStrategyAgent(
        yes_token=YES_TOKEN, 
        no_token=NO_TOKEN, 
        lat=40.7128, 
        lon=-74.0060,
        station_id="KJFK"
    )
    nyc_strat.run_strategy_cycle()

import time
from datetime import datetime

# Persistent Strategy instance for Mexico
mexico_swarm = MexicoWeatherStrategy()

if __name__ == "__main__":
    print("=== NASA POLYMARKET ARBITRAGE SWARM ===")
    while True:
        print(f"\n[{datetime.now()}] 🔄 Beginning New Cycle...")
        try:
            run_satellite_oracle()
        except Exception as e:
            print(f"❌ [FIRE_ERROR] Satellite Oracle Failed: {e}")
            
        try:
            run_weather_oracle()
        except Exception as e:
            print(f"❌ [WEATHER_ERROR] Weather Oracle Failed: {e}")

        try:
            print("\n🇲🇽 [MEXICO SWARM] Evaluating Temperature Arbitrage...")
            mexico_swarm.run_cycle()
        except Exception as e:
            print(f"❌ [MEXICO_ERROR] Mexico Weather Oracle Failed: {e}")
        
        print(f"\n[{datetime.now()}] 💤 Cycle Complete. Sleeping for 300s...")
        time.sleep(300)
