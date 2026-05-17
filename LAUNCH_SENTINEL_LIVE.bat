@echo off
title 🛡️ SENTINEL LIVE ORCHESTRATOR (v28.9) 🛡️
color 0A
echo ===================================================
echo      INITIATING SENTINEL LIVE CAPITAL DEPLOYMENT
echo ===================================================
cd /d "c:\Sentinel_Project"

:: Force UTF-8 Encoding to prevent execution bridge crashes
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

:: Execute the Master Orchestrator
venv\Scripts\python.exe deploy_live.py

pause
