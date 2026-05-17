import requests
import sys

def main():
    print("==================================================")
    print(" [PORT DIAGNOSTIC] PINGING COGNITIVE PORTS")
    print("==================================================")
    
    # 1. Ping Port 8000 (FastAPI Sniper / Execution Bridge)
    try:
        resp = requests.get("http://localhost:8000/status", timeout=2)
        print(f" Port 8000 (Sniper): ONLINE (Status: {resp.status_code})")
        try:
            print(f"  Payload: {resp.json()}")
        except Exception:
            pass
    except Exception as e:
        print(f" Port 8000 (Sniper): OFFLINE ({e})")
        
    # 2. Ping Port 8001 (Risk Agent)
    try:
        resp = requests.get("http://localhost:8001/status", timeout=2)
        print(f" Port 8001 (Risk Agent): ONLINE (Status: {resp.status_code})")
        try:
            print(f"  Payload: {resp.json()}")
        except Exception:
            pass
    except Exception as e:
        print(f" Port 8001 (Risk Agent): OFFLINE ({e})")

    # 3. Check specific check_trade endpoint if available
    try:
        resp = requests.get("http://localhost:8001/check_trade", timeout=2)
        print(f" Port 8001 /check_trade: ONLINE (Status: {resp.status_code})")
    except Exception as e:
        print(f" Port 8001 /check_trade: OFFLINE ({e})")
        
    print("==================================================")

if __name__ == "__main__":
    main()
