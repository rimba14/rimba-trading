import json
from typing import List, Dict, Tuple

class GeoBoundaryMapper:
    """
    Translates raw GPS coordinates (Hotspots) into Polymarket Triggers.
    Uses GeoJSON bounding boxes or simple Lat/Long ranges for specific Regions.
    """
    def __init__(self):
        # Dictionary of pre-defined risk zones for known Polymarket regions
        # Format: { region_name: (lat_min, lat_max, lon_min, lon_max) }
        self.risk_zones = {
            "CALIFORNIA_NORTH": (38.0, 42.0, -124.5, -120.0),
            "CALIFORNIA_SOUTH": (32.5, 35.0, -120.0, -114.0),
            "TEXAS_PANHANDLE": (34.0, 36.5, -103.0, -100.0),
            "Humboldt_County": (40.0, 41.5, -124.5, -123.5)
        }

    def detect_activations(self, fire_df):
        """
        Takes a NASA FIRMS dataframe and counts hotspot activations per zone.
        """
        results = {}
        for zone, bounds in self.risk_zones.items():
            lat_min, lat_max, lon_min, lon_max = bounds
            
            activations = fire_df[
                (fire_df['latitude'] >= lat_min) & (fire_df['latitude'] <= lat_max) &
                (fire_df['longitude'] >= lon_min) & (fire_df['longitude'] <= lon_max)
            ]
            
            results[zone] = {
                "count": len(activations),
                "hotspot_intensities": activations['brightness'].tolist() if 'brightness' in activations else []
            }
        return results

    def add_custom_zone(self, name: str, bbox: Tuple[float, float, float, float]):
        """Adds a new contract-specific zone manually."""
        self.risk_zones[name] = bbox

if __name__ == "__main__":
    import pandas as pd
    mapper = GeoBoundaryMapper()
    
    # Mock fire data near LA
    df = pd.DataFrame([{
        'latitude': 34.05, 'longitude': -118.24, 'brightness': 400.0, 'acq_date': '2026-04-16'
    }])
    
    activations = mapper.detect_activations(df)
    print(f"[MAPPER] Activation Report: {json.dumps(activations, indent=2)}")
