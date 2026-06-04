file_path = r'C:\Sentinel_Project\sentinel_slow_loop.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace local import with aliased import to prevent UnboundLocalError
content = content.replace('import os, json\n                os.makedirs', 'import os as _os, json as _json\n                _os.makedirs')
content = content.replace('with open(f"shap_diagnostics/{symbol}_stagnant.json", "w") as f:\n                    json.dump', 'with open(f"shap_diagnostics/{symbol}_stagnant.json", "w") as f:\n                    _json.dump')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed UnboundLocalError for json module")
