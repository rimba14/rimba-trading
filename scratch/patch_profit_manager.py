file_path = r"C:\Sentinel_Project\profit_manager_v28_34.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

patch_code = """
                import requests
                for pos in all_positions:
                    if pos.sl > 0.0 or pos.tp > 0.0:
                        print(f"[CONSTITUTIONAL_VIOLATION] Physical stops detected on ticket {pos.ticket}. Stripping immediately.")
                        try:
                            requests.post("http://127.0.0.1:8000/strip_stops", json={"ticket": pos.ticket}, timeout=5)
                        except Exception as e:
                            print(f"[STRIP_STOPS_FAIL] Could not strip stops on {pos.ticket}: {e}")
"""

old_target = """                all_positions = list(sentinel_pos) + list(legacy_pos)
                active_tickets = {p.ticket for p in all_positions}"""

new_target = """                all_positions = list(sentinel_pos) + list(legacy_pos)""" + patch_code + """
                active_tickets = {p.ticket for p in all_positions}"""

content = content.replace(old_target, new_target)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched profit_manager_v28_34.py")
