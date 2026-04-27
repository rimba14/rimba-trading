import requests
import json

def search_markets(query="rain"):
    """
    Searches Polymarket Gamma API for active markets matching the query.
    """
    print(f"🔎 [DISCOVERY] Searching for '{query}' markets...")
    
    # Gamma API for market discovery
    url = f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=10&search={query}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            markets = response.json()
            if not markets:
                print("ℹ️ No active markets found for that query.")
                return
            
            print(f"\n{'QUESTION':<60} | {'TOKEN_ID (YES)':<15} | {'TOKEN_ID (NO)'}")
            print("-" * 120)
            for m in markets:
                question = m.get('question', 'Unknown')
                # Outcome Assets contain the real Token IDs for CLOB
                tokens = m.get('outcomeAssets', [])
                if len(tokens) >= 2:
                    # Usually [YES_TOKEN_ID, NO_TOKEN_ID]
                    yes_id = tokens[0]
                    no_id = tokens[1]
                    print(f"{question[:58]:<60} | {yes_id[:15]}... | {no_id[:15]}...")
                    # Print full IDs for the first result to help the user
                    print(f"   [FULL YES]: {yes_id}")
                    print(f"   [FULL NO ]: {no_id}")
                    print(" " + "-"*118)
        else:
            print(f"❌ Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "rain"
    search_markets(query)
