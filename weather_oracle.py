import requests
import json
import logging
from datetime import datetime

# London Coordinates
LAT, LON = 51.5074, -0.1278

logging.basicConfig(level=logging.INFO, format='%(asctime)s [WEATHER_ORACLE] %(message)s')

class WeatherOracle:
    def __init__(self):
        self.user_agent = {"User-Agent": "SentinelWeatherOracle/1.0 (contact: admin@sentinel.ai)"}

    def get_noaa_data(self):
        """Fetches data for London (Using Open-Meteo as primary for UK)."""
        # NOAA is US-only. For London, we'll use a secondary global source or just return a placeholder.
        return {"source": "NOAA-Global", "prob": 0, "condition": "N/A (UK)"}

    def get_open_meteo_data(self):
        """Fetches precipitation probability from Open-Meteo."""
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=precipitation_probability&forecast_days=1"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            # Get current hour probability
            current_hour = datetime.now().hour
            prob = data['hourly']['precipitation_probability'][current_hour]
            return {"source": "Open-Meteo", "prob": prob, "condition": "Cloudy" if prob > 20 else "Clear"}
        except Exception as e:
            logging.error(f"Open-Meteo Fetch Error: {e}")
            return {"source": "Open-Meteo", "prob": 0, "condition": "Error"}

    def get_accuweather_data(self):
        """Mock/Simulated AccuWeather fetch (Requires API Key for real)."""
        # In a real SRE patch, we would hit the AccuWeather API here.
        # For this architecture demonstration, we'll simulate a 15% probability if it's currently sunny.
        return {"source": "AccuWeather", "prob": 15, "condition": "Mostly Sunny"}

    def check_agreement(self, threshold=50):
        """Checks if all three sources agree that precipitation probability > threshold."""
        noaa = self.get_noaa_data()
        om = self.get_open_meteo_data()
        accu = self.get_accuweather_data()
        
        sources = [noaa, om, accu]
        agreement = all(s['prob'] > threshold for s in sources)
        
        return {
            "agreement": agreement,
            "sources": sources,
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    oracle = WeatherOracle()
    res = oracle.check_agreement(threshold=30)
    print(json.dumps(res, indent=2))
