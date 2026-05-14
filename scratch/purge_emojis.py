import os

def purge_non_ascii(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Keep only ASCII characters
    clean_content = "".join(i for i in content if ord(i) < 128)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(clean_content)
    print(f"Purged all non-ASCII from {filepath}")

if __name__ == "__main__":
    purge_non_ascii(r'C:\Sentinel_Project\profit_manager.py')
