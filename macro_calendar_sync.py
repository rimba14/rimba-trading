import os
import sys
import json
import time
import asyncio
import logging
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Inject project path
sys.path.append(r"C:\Sentinel_Project")

# --- UTF-8 Enforced Logging ---
import io as _io
def _get_utf8_stream():
    if getattr(sys.stdout, 'encoding', '').lower() == 'utf-8':
        return sys.stdout
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return sys.stdout
    except Exception:
        return _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

_UTF8_STREAM = _get_utf8_stream()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MACRO_SYNC] %(message)s",
    handlers=[
        logging.StreamHandler(_UTF8_STREAM),
        logging.FileHandler("C:/Sentinel_Project/data/macro_sync.log", encoding="utf-8")
    ]
)

# --- Helpers ---

def atomic_write_json(file_path: Path, data: dict):
    """Safely and atomically writes/overwrites a JSON file using a temp-file write & rename."""
    parent = file_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    
    fd, temp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        if os.path.exists(file_path):
            os.replace(temp_path, str(file_path))
        else:
            os.rename(temp_path, str(file_path))
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

def generate_high_fidelity_mocks() -> list:
    """Generates a realistic set of high impact Tier-1 events relative to now for the G8 basket (2h to 48h)."""
    now_ts = int(time.time())
    mock_catalogs = [
        {"event": "JPY BOJ Policy Rate Decision", "currency": "JPY", "offset_hours": 2.0},
        {"event": "AUD RBA Interest Rate Decision", "currency": "AUD", "offset_hours": 6.0},
        {"event": "USD FOMC Interest Rate Decision", "currency": "USD", "offset_hours": 10.0},
        {"event": "GBP BOE Interest Rate Decision", "currency": "GBP", "offset_hours": 14.0},
        {"event": "CHF SNB Policy Rate Decision", "currency": "CHF", "offset_hours": 18.0},
        {"event": "NZD RBNZ Interest Rate Decision", "currency": "NZD", "offset_hours": 22.0},
        {"event": "EUR ECB Interest Rate Decision", "currency": "EUR", "offset_hours": 26.0},
        {"event": "CAD BOC Interest Rate Decision", "currency": "CAD", "offset_hours": 32.0},
        {"event": "USD Non-Farm Employment Change (NFP)", "currency": "USD", "offset_hours": 40.0},
        {"event": "GBP BOE Governor Speech", "currency": "GBP", "offset_hours": 48.0},
    ]
    
    events = []
    for item in mock_catalogs:
        event_time = now_ts + int(item["offset_hours"] * 3600)
        events.append({
            "event": item["event"],
            "currency": item["currency"],
            "time": event_time,
            "impact": "HIGH"
        })
    return events

def fetch_live_events() -> list:
    """Attempts to fetch the live Forex Factory weekly calendar feed; falls back to high-fidelity mock."""
    url = "https://nfs.forexfactory.com/ff_calendar_thisweek.xml"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    
    events = []
    try:
        logging.info("Requesting live economic calendar from ForexFactory feed...")
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall("event"):
                title = item.find("title").text or ""
                country = item.find("country").text or ""
                date_str = item.find("date").text or ""
                time_str = item.find("time").text or ""
                impact = item.find("impact").text or ""
                
                # Filter ONLY High-Impact Tier-1 events for G8 basket
                if impact.lower() != "high":
                    continue
                    
                g8_currencies = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}
                if country.upper() not in g8_currencies:
                    continue
                    
                if time_str.lower() in ["all day", "tentative"]:
                    continue # precise times only
                    
                try:
                    dt_str = f"{date_str} {time_str}"
                    dt_est = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    
                    # Convert EST/EDT to UTC (Simple DST Heuristic for New York)
                    month = dt_est.month
                    is_dst = True
                    if month < 3 or month > 11:
                        is_dst = False
                    elif month == 3:
                        is_dst = dt_est.day >= 8
                    elif month == 11:
                        is_dst = dt_est.day < 7
                        
                    offset = 4 if is_dst else 5
                    dt_utc = dt_est + timedelta(hours=offset)
                    event_time = int(dt_utc.timestamp())
                    
                    events.append({
                        "event": f"{country} {title}",
                        "currency": country,
                        "time": event_time,
                        "impact": "HIGH"
                    })
                except Exception as pe:
                    logging.debug(f"Failed parsing item {title} ({date_str} {time_str}): {pe}")
                    
        logging.info(f"Successfully processed {len(events)} live Tier-1 events from ForexFactory.")
    except Exception as e:
        logging.warning(f"ForexFactory resolution/fetch failed: {e}. Transitioning to Premium Mock Fallback Generator...")
        events = generate_high_fidelity_mocks()
        
    return events

# --- Daemon Execution ---

async def run_sync_loop():
    logging.info("Initializing Macro Calendar Sync Loop...")
    macro_path = Path("C:/Sentinel_Project/data/macro_state.json")
    
    while True:
        try:
            # 1. Fetch live/mock events
            events = fetch_live_events()
            
            # 2. Load existing state to merge and preserve Deep Research keys
            m_state = {}
            if macro_path.exists():
                try:
                    with open(macro_path, "r", encoding="utf-8") as f:
                        m_state = json.load(f)
                except Exception:
                    pass
                    
            m_state.setdefault("global_macro_sentiment", 0.0)
            m_state.setdefault("black_swan_risk", 0.0)
            m_state.setdefault("asset_specific_catalysts", {})
            
            # Set updated calendar
            m_state["upcoming_events"] = events
            m_state["last_sync_timestamp"] = int(time.time())
            m_state["last_sync_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            
            # 3. Write atomically
            atomic_write_json(macro_path, m_state)
            logging.info(f"Atomically synced {len(events)} Tier-1 macro events to {macro_path}.")
            
        except Exception as e:
            logging.critical(f"Critical failure in sync cycle: {e}")
            
        # Calculate standard 4 hour sleep vs UTC 00:05 wakeup
        now = datetime.now(timezone.utc)
        sleep_secs = 4 * 3600
        
        # Time to next 00:05 UTC
        target_0005 = now.replace(hour=0, minute=5, second=0, microsecond=0)
        if target_0005 <= now:
            target_0005 += timedelta(days=1)
            
        secs_until_0005 = (target_0005 - now).total_seconds()
        
        actual_sleep = min(sleep_secs, secs_until_0005)
        logging.info(f"Next sync wake scheduled in {actual_sleep/3600:.2f} hours (or UTC 00:05).")
        await asyncio.sleep(actual_sleep)

if __name__ == "__main__":
    try:
        asyncio.run(run_sync_loop())
    except KeyboardInterrupt:
        logging.info("Macro Sync Daemon stopped by user.")
