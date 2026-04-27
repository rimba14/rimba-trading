@echo off
setlocal
set "TASK_NAME=Adaptive_Sentinel_EOD"
set "EXEC_PATH=%~dp0venv\Scripts\python.exe"
set "SCRIPT_PATH=%~dp0eod_report.py"

:: --- ADMIN CHECK ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script requires administrative privileges.
    echo Please right-click and "Run as Administrator".
    pause
    exit /b 1
)

:: --- CREATE SCHEDULED TASK ---
echo [SYSTEM] Creating Daily EOD Task at 17:00...
schtasks /create /tn "%TASK_NAME%" /tr "\"%EXEC_PATH%\" \"%SCRIPT_PATH%\"" /sc DAILY /st 17:00 /f

if %errorLevel% equ 0 (
    echo [SUCCESS] Task "%TASK_NAME%" created successfully.
    echo The EOD report will fire daily at 17:00 Server Time.
) else (
    echo [FAILED] Could not create scheduled task.
)

pause
