@echo off
setlocal enabledelayedexpansion

:: Hardware Restoration Pivot | Staging to C: Migration
:: Objective: Push data from staging drive to C:\Sentinel_Project and rebuild environment.

set STAGING_DRIVE=X:
set TARGET_DIR=C:\Sentinel_Project
set ARCTIC_DIR=C:\sentinel_arctic

echo.
echo ==============================================
echo == INITIATING HARDWARE RESTORATION PIVOT    ==
echo ==============================================
echo.

:: 1. CHECK STAGING DRIVE
if not exist %STAGING_DRIVE%\ (
    echo [!] ERROR: Staging drive %STAGING_DRIVE% not found.
    echo Please ensure the staging drive is connected and mapped to %STAGING_DRIVE%.
    set /p STAGING_DRIVE="Enter the correct staging drive letter (e.g. F:): "
)

echo [*] Source Staging: %STAGING_DRIVE%\Sentinel_Staging
echo [*] Target Root:   %TARGET_DIR%

:: 2. EXECUTE TRANSFER (Robocopy)
echo [*] Transferring Project Root...
robocopy "%STAGING_DRIVE%\Sentinel_Staging\project_root" "%TARGET_DIR%" /E /Z /R:5 /W:5 /MT:32 /XD .git .agents .gemini brain tmp __pycache__ venv

echo [*] Transferring ArcticDB Storage...
robocopy "%STAGING_DRIVE%\Sentinel_Staging\arctic_db" "%ARCTIC_DIR%" /E /Z /R:5 /W:5 /MT:32

:: 3. SCORCHED EARTH VENV REBUILD
echo [*] Initiating Scorched Earth Venv Rebuild...
if exist "%TARGET_DIR%\venv" (
    echo [*] Deleting existing venv...
    rd /s /q "%TARGET_DIR%\venv"
)

echo [*] Creating fresh venv...
cd /d "%TARGET_DIR%"
python -m venv venv

echo [*] Activating venv and installing requirements...
call venv\Scripts\activate.bat
if exist "requirements.txt" (
    pip install --upgrade pip
    pip install -r requirements.txt
) else (
    echo [!] WARNING: requirements.txt not found. Installing core dependencies...
    pip install arcticdb pandas numpy requests
)

:: 4. RUN PATH REFACTORING
echo [*] Running path refactoring utility...
python refactor_paths.py

echo.
echo ==============================================
echo == RESTORATION COMPLETE. RUN VERIFICATION.  ==
echo ==============================================
pause
