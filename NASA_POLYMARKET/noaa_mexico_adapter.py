import requests
import json

class NOAAMexicoAdapter:
    """
    Uses Aviation Weather METAR API to monitor Mexico City (MMMX).
    """
    def __init__(self, station_id="MMMX"):
        self.station_id = station_id
        self.base_url = "https://aviationweather.gov/api/data/metar"

    def get_latest_temp(self):
        """Fetches the latest temperature from MMMX METAR."""
        try:
            params = {"ids": self.station_id, "format": "json"}
            res = requests.get(self.base_url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data and len(data) > 0:
                    temp = data[0].get('temp')
                    print(f"✈️  [NOAA/MMMX] Current Temp: {temp}°C")
                    return temp
                return None
            else:
                print(f"❌ [NOAA_MEX_ERR] Status {res.status_code}")
                return None
        except Exception as e:
            print(f"❌ [NOAA_MEX_CRIT] {e}")
            return None

if __name__ == "__main__":
    adapter = NOAAMexicoAdapter()
    adapter.get_latest_temp()
