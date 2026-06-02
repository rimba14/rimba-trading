import re
file_path = r'C:\Sentinel_Project\get_top_5.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Change threshold from 0.60 to 0.50 to guarantee top 5
content = content.replace('if conviction > 0.60:', 'if conviction > 0.50:')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Lowered threshold to 0.50")
