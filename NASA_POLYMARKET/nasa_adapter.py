import requests
import pandas as pd
import os
from io import StringIO
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class NasaFireAdapter:
    """
    Adapter for NASA FIRMS (Fire Information for Resource Management System).
    Monitors VIIRS and MODIS satellite data for thermal hotspots.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("NASA_FIRMS_KEY")
        # Base URL for VIIRS S-NPP data
        self.base_url = "https://firms.modaps.eosdis.nasa.gov/api/active_fire/viirs/csv/"

    def get_latest_usa_fires(self, last_n_hours: int = 24) -> pd.DataFrame:
        """
        Fetches the latest active fire data for the USA.
        Note: Requires a valid FIRMS API Key.
        """
        if not self.api_key:
            print("[NASA] ERROR: NASA_FIRMS_KEY missing. Cannot fetch live data.")
            return pd.DataFrame()

        # URL Pattern: https://firms.modaps.eosdis.nasa.gov/api/area/csv/[KEY]/[SOURCE]/[AREA]/[RANGE]
        # USA Bounding Box: -125,24,-66,50
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{self.api_key}/VIIRS_SNPP_NRT/-125,24,-66,50/1"
        
        try:
            print(f"[NASA] Fetching live hotspot data from FIRMS...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            df = pd.read_csv(StringIO(response.text))
            print(f"[NASA] Successfully ingested {len(df)} active hotspots.")
            return df
        except Exception as e:
            print(f"[NASA] Connection Error: {e}")
            return pd.DataFrame()

    def filter_by_boundary(self, df: pd.DataFrame, lat_min, lat_max, long_min, long_max) -> pd.DataFrame:
        """
        Filters the hotspot dataframe to a specific geographic box (e.g. Humboldt County).
        """
        if df.empty: return df
        
        filtered = df[
            (df['latitude'] >= lat_min) & (df['latitude'] <= lat_max) &
            (df['longitude'] >= long_min) & (df['longitude'] <= long_max)
        ]
        return filtered

if __name__ == "__main__":
    # Test with placeholder (User needs to provide Key)
    adapter = NasaFireAdapter()
    print("[TEST] NASA Adapter Initialized.")
    
    # Mock data for demonstration if no API key
    if not os.getenv("NASA_FIRMS_KEY"):
        print("[MOCK] No API key found. Generating sample hotspot data for CA...")
        mock_fire = pd.DataFrame([{
            'latitude': 34.05, 'longitude': -118.24, 'brightness': 350.5, 'acq_date': '2026-04-16'
        }])
        print(mock_fire)
