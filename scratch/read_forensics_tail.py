import json

def tail_forensics():
    path = r"C:\Sentinel_Project\sentinel_forensics.json"
    with open(path, "r") as f:
        data = json.load(f)
    print("Last 3 forensics entries:")
    for item in data[-3:]:
        print(json.dumps(item, indent=2))

if __name__ == "__main__":
    tail_forensics()
