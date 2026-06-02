import re
file_path = r'C:\Sentinel_Project\sentinel_slow_loop.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the zero-variance check with a disabled version
old_logic = "if pd.isna(price_variance) or price_variance == 0.0 or cumulative_volume == 0:"
new_logic = "if False: # pd.isna(price_variance) or price_variance == 0.0 or cumulative_volume == 0:"

new_content = content.replace(old_logic, new_logic)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Disabled ZERO-VARIANCE DETECTED bypass in sentinel_slow_loop.py")
