@echo off
TITLE ADAPTIVE SENTINEL | VISUAL COMMAND CENTER
echo [SYSTEM] Forcing Directory to C:\Sentinel_Project...
C:
cd \Sentinel_Project

echo [SYSTEM] Activating SRE Virtual Environment...
call C:\Sentinel_Project\venv\Scripts\activate.bat

echo [SYSTEM] Launching Standalone Streamlit Dashboard...
cmd /k "C:\Sentinel_Project\venv\Scripts\python.exe -m streamlit run sentinel_dashboard.py --server.port 8501 --server.headless false"
