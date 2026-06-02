import re
file_path = r'C:\Sentinel_Project\get_top_5.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# filter out crypto if needed
content = content.replace('if conviction >= 0.50:', 'if conviction >= 0.50 and "BTC" not in base_sym and "ETH" not in base_sym and "NAS100" not in base_sym:')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Filtered out BTC/ETH/NAS100")
