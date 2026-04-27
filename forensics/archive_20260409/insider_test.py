import urllib.request
import re

def get_insider_data():
    url = "http://openinsider.com/latest-cluster-buys"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching OpenInsider: {e}")
        return []
        
    # OpenInsider ticker format: <a href="/ticker">TICKER</a>
    # It must be 1-5 uppercase letters.
    # Exclude matches containing "industry" or lower case letters
    raw_matches = re.findall(r'<td><b><a href="/([^"]+)">', html)
    if not raw_matches:
        raw_matches = re.findall(r'<td><a href="/([^"]+)">', html)
        
    tickers = []
    for match in raw_matches:
        # Check if match is a valid stock ticker (only uppercase letters, 1 to 5 chars length max)
        if re.match(r'^[A-Z]{1,5}$', match):
            tickers.append(match)
            
    # keep unique order
    unique_tickers = list(dict.fromkeys(tickers))
    print(f"Cluster Buys Tickers: {unique_tickers[:10]}")
    return unique_tickers

get_insider_data()
