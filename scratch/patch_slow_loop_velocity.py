import re

file_path = r"C:\Sentinel_Project\sentinel_slow_loop.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove _fetch_ofi_velocity function entirely
content = re.sub(
    r"def _fetch_ofi_velocity.*?return 0\.0\s*",
    "",
    content,
    flags=re.DOTALL
)

# 2. Remove ofi_velocity assignment
content = re.sub(
    r"^\s*ofi_velocity\s*=\s*_fetch_ofi_velocity.*?\n",
    "",
    content,
    flags=re.MULTILINE
)

# 3. Remove "ofi_velocity": ... lines
content = re.sub(
    r"^\s*\"ofi_velocity\":.*?\n",
    "",
    content,
    flags=re.MULTILINE
)

# 4. Remove INDEX_STARVATION_VETO block
content = re.sub(
    r"^\s*if symbol\.upper\(\) in _INDICES and _INDEX_STARVATION_DETECTED:.*?\n\s*logging\.warning.*?Blocking all index entries\.\"\)\n",
    "",
    content,
    flags=re.MULTILINE
)

# 5. Remove Retrospective consensus gate tightening block
content = re.sub(
    r"^\s*# Rule 2\.2: Retrospective consensus gate tightening if tick starvation occurred.*?\n\s*if _TICK_STARVATION_DETECTED:.*?\n\s*logging\.warning.*?retrospectively!\"\)\n",
    "",
    content,
    flags=re.MULTILINE
)

# 6. Remove definitions of _TICK_STARVATION_DETECTED
content = re.sub(
    r"^\s*_TICK_STARVATION_DETECTED\s*=\s*(True|False).*?\n",
    "",
    content,
    flags=re.MULTILINE
)
content = re.sub(
    r"^\s*_INDEX_STARVATION_DETECTED\s*=\s*(True|False).*?\n",
    "",
    content,
    flags=re.MULTILINE
)

# 7. Remove them from globals
content = re.sub(r",\s*_TICK_STARVATION_DETECTED", "", content)
content = re.sub(r",\s*_INDEX_STARVATION_DETECTED", "", content)

# 8. Clean up tighten argument in check_consensus
content = re.sub(
    r"tighten=\(_TICK_STARVATION_DETECTED or is_this_symbol_starved\)",
    "tighten=is_this_symbol_starved",
    content
)

# 9. Clean up is_degraded definition
content = re.sub(
    r"or _TICK_STARVATION_DETECTED ",
    "",
    content
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied to sentinel_slow_loop.py")
