import requests
import json
try:
    resp = requests.get("http://localhost:8001/api/weather", timeout=5)
    print(json.dumps(resp.json(), indent=2))
except Exception as e:
    print(f"Server not responding: {e}")
