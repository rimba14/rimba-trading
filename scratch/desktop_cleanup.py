import os

desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
files_to_delete = [
    'Master_Launch.bat', 
    'Run_77_Matrix.bat', 
    'Run_Watchdog.bat', 
    'Sentinel Cognition.lnk'
]

log = []
for f in files_to_delete:
    path = os.path.join(desktop, f)
    if os.path.exists(path):
        try:
            os.remove(path)
            log.append(f"DELETED: {f}")
        except Exception as e:
            log.append(f"ERROR deleting {f}: {e}")
    else:
        log.append(f"NOT FOUND: {f}")

# Create new Ignite_Sentinel.bat
batch_content = """@echo off
TITLE Adaptive Sentinel Matrix Ignition
color 0A
echo ===================================================
echo     INITIATING ADAPTIVE SENTINEL STARTUP SEQUENCE
echo ===================================================
cd /d C:\Sentinel_Project
echo [SYSTEM] Activating Virtual Environment...
call venv\Scripts\activate.bat
echo [SYSTEM] Virtual Environment Active.
echo [SYSTEM] Handing over to Master Bootstrapper...
python boot_matrix.py
pause
"""

new_batch_path = os.path.join(desktop, 'Ignite_Sentinel.bat')
with open(new_batch_path, 'w') as f:
    f.write(batch_content)
log.append(f"DEPLOYED: Ignite_Sentinel.bat")

print("\n".join(log))
