@echo off
color 0A
title Sentinel Cognition Dashboard
cd /d "%~dp0"

:: Activate virtual environment
call venv\Scripts\activate

:: Run the audit script
python audit_cognition.py

:: Keep window open
echo.
echo Press any key to close the dashboard...
pause >nul
