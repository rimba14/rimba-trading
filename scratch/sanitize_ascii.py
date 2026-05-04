import sys
import os

def sanitize_to_ascii(file_path):
    with open(file_path, 'rb') as f:
        content = f.read().decode('utf-8', errors='ignore')
    
    # Common replacements for non-ASCII characters seen in the logs
    replacements = {
        '✅': '[OK]',
        '❌': '[FAIL]',
        '──': '--',
        '—': '-',
        '→': '->',
        '🚨': '[ALERT]',
        '⚙️': '[CONFIG]',
    }
    
    for char, replacement in replacements.items():
        content = content.replace(char, replacement)
    
    # Filter out remaining non-ASCII
    sanitized = "".join(i if ord(i) < 128 else " " for i in content)
    
    with open(file_path, 'w', encoding='ascii') as f:
        f.write(sanitized)
    print(f"Sanitized {file_path} to ASCII.")

if __name__ == "__main__":
    sanitize_to_ascii(sys.argv[1])
