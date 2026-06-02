file_path = r"C:\Sentinel_Project\pre_execution_gate.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

bad_code = """        elif now_utc.weekday() == 5 or now_utc.weekday() == 6:
            return reject("Gate 7 Failed: Weekend Blackout (Saturday/Sunday)")"""

good_code = """        elif now_utc.weekday() == 5 or (now_utc.weekday() == 6 and now_utc.hour < 22):
            return reject("Gate 7 Failed: Weekend Blackout (Saturday/Sunday daytime)")"""

if bad_code in content:
    content = content.replace(bad_code, good_code)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched pre_execution_gate.py to allow Sunday > 22:00 UTC.")
