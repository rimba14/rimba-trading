import re
file_path = r'C:\Sentinel_Project\get_top_5.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace xgb_p with meta_conviction
content = content.replace('float(row.get("xgb_p", 0.5))', 'float(row.get("meta_conviction", row.get("xgb_p", 0.5)))')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patched get_top_5.py to use meta_conviction")
