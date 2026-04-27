import requests
import os

class AccuWeatherAdapter:
    def __init__(self, location_key="242560"): # Mexico City
        self.location_key = location_key
        self.api_key = os.getenv("ACCUWEATHER_API_KEY")
        self.base_url = "http://dataservice.accuweather.com"

    def get_daily_high(self):
        """Fetches the daily high temperature from AccuWeather."""
        if not self.api_key:
            print("⚠️  [ACCUWEATHER] Missing API Key. Returning Mock.")
            return 22.5 # Mock high above 21C
            
        try:
            url = f"{self.base_url}/forecasts/v1/daily/1day/{self.location_key}"
            params = {"apikey": self.api_key, "metric": "true"}
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                temp = data.get('DailyForecasts', [{}])[0].get('Temperature', {}).get('Maximum', {}).get('Value')
                print(f"☀️  [ACCUWEATHER] Daily High: {temp}°C")
                return temp
            else:
                print(f"❌ [ACCU_ERR] Status {res.status_code}")
                return None
        except Exception as e:
            print(f"❌ [ACCU_CRIT] {e}")
            return None

if __name__ == "__main__":
    adapter = AccuWeatherAdapter()
    adapter.get_daily_high()
