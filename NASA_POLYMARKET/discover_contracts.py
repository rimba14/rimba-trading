import requests
import json

def search_markets(query="rain"):
    """
    Searches Polymarket Gamma API for active markets matching the query.
    """
    print(f"[DISCOVERY] Searching for '{query}' markets...")
    
    # Correct Gamma API endpoint for public search
    url = f"https://gamma-api.polymarket.com/public-search?q={query}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            search_results = response.json()
            # public-search returns { "events": [...], "markets": [...], "profiles": [...] }
            markets = search_results.get('markets', [])
            
            if not markets:
                print("INFO: No active markets found for that query.")
                return
            
            print(f"\n{'QUESTION':<60} | {'TOKEN_ID (YES)':<15} | {'TOKEN_ID (NO)'}")
            print("-" * 120)
            for m in markets:
                if m.get('active') and not m.get('closed'):
                    question = m.get('question', 'Unknown')
                    tokens = m.get('clobTokenIds', [])
                    if len(tokens) >= 2:
                        yes_id = tokens[0]
                        no_id = tokens[1]
                        print(f"{question[:58]:<60} | {yes_id[:15]}... | {no_id[:15]}...")
                        print(f"   [FULL YES]: {yes_id}")
                        print(f"   [FULL NO ]: {no_id}")
                        print(" " + "-"*118)
        else:
            print(f"ERROR: {response.status_code}")
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "rain"
    search_markets(query)
