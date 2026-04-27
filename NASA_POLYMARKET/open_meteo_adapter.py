import requests
import os

class OpenMeteoAdapter:
    def __init__(self, lat=19.4326, lon=-99.1332):
        self.lat = lat
        self.lon = lon
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    def get_daily_high(self):
        """Fetches the daily high temperature for the specified location."""
        try:
            params = {
                "latitude": self.lat,
                "longitude": self.lon,
                "daily": "temperature_2m_max",
                "timezone": "auto"
            }
            res = requests.get(self.base_url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                # Get the first day's max temp
                temp = data.get('daily', {}).get('temperature_2m_max', [None])[0]
                print(f"🌡️  [OPEN-METEO] Daily High: {temp}°C")
                return temp
            else:
                print(f"❌ [METEO_ERR] Status {res.status_code}")
                return None
        except Exception as e:
            print(f"❌ [METEO_CRIT] {e}")
            return None

if __name__ == "__main__":
    adapter = OpenMeteoAdapter()
    adapter.get_daily_high()
