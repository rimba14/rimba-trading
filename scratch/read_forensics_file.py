import json

def check_forensics():
    path = r"C:\Sentinel_Project\sentinel_forensics.json"
    with open(path, "r") as f:
        data = json.load(f)
    print(f"Total entries in forensics: {len(data)}")
    if isinstance(data, dict):
        print("Keys:", list(data.keys())[:10])
        for k, v in data.items():
            if any(str(t) in k or str(t) in str(v) for t in [1286047526, 1286047548, 1288444186]):
                print(f"\nFound match for ticket in key {k}:")
                print(json.dumps(v, indent=2))
    elif isinstance(data, list):
        print("Type is list. First item keys:", list(data[0].keys()) if data else "empty")
        for item in data:
            item_str = json.dumps(item)
            if any(str(t) in item_str for t in [1286047526, 1286047548, 1288444186]):
                print("\nFound match for ticket in list item:")
                print(json.dumps(item, indent=2))

if __name__ == "__main__":
    check_forensics()
