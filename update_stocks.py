import re
import os

filepath = r'C:\Users\Administrator\.gemini\antigravity\brain\12325980-a53b-4d3f-8c1d-135ccefcf2eb\.system_generated\steps\756\output.txt'
with open(filepath, 'r') as f:
    lines = [line.strip() for line in f if line.strip()]

stocks = []
for s in lines:
    # Filter out forex pairs, indices, bounds, lengths that clearly arent stocks
    if '+' in s or '.' in s or '-' in s or s.endswith('USD') or s.endswith('JPY') or s.endswith('EUR') or s.endswith('GBP') or s.endswith('CAD') or s.endswith('AUD') or s.endswith('NZD') or s.endswith('CHF'):
        continue
    if len(s) > 6:
        continue
    if s in ['EUB10Y', 'EUB2Y', 'EUB30Y', 'EUB5Y', 'LongGilt', 'Nikkei225']:
        continue
    stocks.append(s)

print(f"Extracted {len(stocks)} symbols.")
stocks_str = ', '.join([f'"{s}"' for s in stocks])

def update_file(path):
    with open(path, 'r') as f:
        content = f.read()
    
    # We will search for the "Crypto" comment and insert our stocks block right before it
    new_content = re.sub(r'(\s*# Crypto\s*)', r'\n    # Global Share CFDs\n    ' + stocks_str + r',\n\g<1>', content)
    
    with open(path, 'w') as f:
        f.write(new_content)
    print(f"Updated {path}")

update_file(r'c:\Users\Administrator\Downloads\vantage_execute.py')
update_file(r'c:\Users\Administrator\Downloads\vantage_analysis.py')
