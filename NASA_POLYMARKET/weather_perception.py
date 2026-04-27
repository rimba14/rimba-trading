import requests
import os
import json
import pandas as pd
from datetime import datetime

class WeatherConsensusOracle:
    """
    TRIPLE-CHECK WEATHER ORACLE
    Aggregates NOAA, Open-Meteo, and WeatherAPI to detect mispriced weather events.
    """
    def __init__(self, lat=40.7128, lon=-74.0060): # Default: New York
        self.lat = lat
        self.lon = lon
        self.weatherapi_key = os.getenv("WEATHERAPI_KEY")
        
    def get_noaa_forecast(self):
        """NOAA Public API (Gov)"""
        try:
            # First, get the station/grid info
            header = {'User-Agent': 'NASA_Poly_Bot/1.0'}
            res = requests.get(f"https://api.weather.gov/points/{self.lat},{self.lon}", headers=header, timeout=5)
            if res.status_code != 200: return None
            
            grid_url = res.json()['properties']['forecast']
            forecast_res = requests.get(grid_url, headers=header, timeout=5)
            if forecast_res.status_code != 200: return None
            
            # Extract current/next-gen forecast
            return forecast_res.json()['properties']['periods'][0]
        except Exception as e:
            print(f"[NOAA_ERR] {e}")
            return None

    def get_open_meteo_forecast(self):
        """Open-Meteo (Free/Open Data)"""
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={self.lat}&longitude={self.lon}&current=precipitation,temperature_2m&hourly=precipitation_probability"
            res = requests.get(url, timeout=5)
            if res.status_code != 200: return None
            return res.json()
        except Exception as e:
            print(f"[METEO_ERR] {e}")
            return None

    def get_weatherapi_forecast(self):
        """WeatherAPI.com (Commercial Free Tier)"""
        if not self.weatherapi_key:
            return {"mock": True, "condition": "Cloudy", "precip_mm": 0.0}
            
        try:
            url = f"http://api.weatherapi.com/v1/forecast.json?key={self.weatherapi_key}&q={self.lat},{self.lon}&days=1&aqi=no"
            res = requests.get(url, timeout=5)
            if res.status_code != 200: return None
            return res.json()
        except Exception as e:
            print(f"[WAPI_ERR] {e}")
            return None

    def check_triple_agreement(self, target_event="rain"):
        """
        Consensus Logic: Flip to YES only if ALL 3 agree.
        """
        results = []
        
        # 1. NOAA Check
        noaa = self.get_noaa_forecast()
        if noaa:
            noaa_rain = "rain" in noaa.get('shortForecast', '').lower() or "shower" in noaa.get('shortForecast', '').lower()
            results.append(noaa_rain)
            print(f" -> NOAA: {'RAIN' if noaa_rain else 'DRY'}")
        
        # 2. Open-Meteo Check
        om = self.get_open_meteo_forecast()
        if om:
            om_rain = om.get('current', {}).get('precipitation', 0) > 0
            # Also check probability for next hour
            prob = om.get('hourly', {}).get('precipitation_probability', [0])[0]
            om_rain = om_rain or prob > 70
            results.append(om_rain)
            print(f" -> Open-Meteo: {'RAIN' if om_rain else 'DRY'} (Prob: {prob}%)")
            
        # 3. WeatherAPI Check
        wapi = self.get_weatherapi_forecast()
        if wapi:
            if "mock" in wapi:
                wapi_rain = False # Mocking dry
            else:
                wapi_rain = wapi.get('current', {}).get('precip_mm', 0) > 0
            results.append(wapi_rain)
            print(f" -> WeatherAPI: {'RAIN' if wapi_rain else 'DRY'}")

        # Final Consensus
        if len(results) < 3:
            print("⚠️ [CONSENSUS] Incomplete data from one or more APIs.")
            return False
            
        consensus = all(results)
        if consensus:
            print("🚀 [CONSENSUS] ALIGNED: All 3 APIs agree on YES.")
        else:
            print("⚖️ [CONSENSUS] Neutral/Muddled. Staying in NO bias.")
            
        return consensus

if __name__ == "__main__":
    oracle = WeatherConsensusOracle()
    print("🧠 [WEATHER ORACLE] Cold-booting consensus layer...")
    is_yes = oracle.check_triple_agreement("rain")
    print(f"Final Verdict: {'YES' if is_yes else 'NO'}")
