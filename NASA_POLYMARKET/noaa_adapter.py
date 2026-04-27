import requests
import json
import os

class NOAAStationAdapter:
    """
    Station-level monitoring for hyper-local weather consensus.
    Uses public NOAA endpoints to monitor specific ASOS/AWOS stations.
    """
    def __init__(self, station_id="KJFK"):
        self.station_id = station_id
        self.base_url = "https://api.weather.gov"
        self.headers = {'User-Agent': 'NASA_Poly_Bot/1.0'}

    def get_latest_observations(self):
        """Fetches latest 1-hour observations from specified station."""
        print(f"🛰️  [NOAA] Fetching observations for station: {self.station_id}")
        url = f"{self.base_url}/stations/{self.station_id}/observations/latest"
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                props = data.get('properties', {})
                return {
                    "timestamp": props.get('timestamp'),
                    "temperature": props.get('temperature', {}).get('value'),
                    "precipitation_last_hour": props.get('precipitationLastHour', {}).get('value'),
                    "description": props.get('textDescription')
                }
            else:
                print(f"❌ [NOAA_ERR] Status {res.status_code}")
                return None
        except Exception as e:
            print(f"❌ [NOAA_CRIT] {e}")
            return None

if __name__ == "__main__":
    adapter = NOAAStationAdapter("KJFK")
    data = adapter.get_latest_observations()
    print(json.dumps(data, indent=2))
