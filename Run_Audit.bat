@echo off
color 0A
title [ ADAPTIVE SENTINEL - MASTER DASHBOARD ]

echo.
echo  ##########################################################
echo  #                                                        #
echo  #          ADAPTIVE SENTINEL - MASTER DASHBOARD          #
echo  #          ------------------------------------          #
echo  #          CPU-Optimized Dual-Loop Architecture          #
echo  #                                                        #
echo  ##########################################################
echo.

set PROJECT_ROOT=C:\Sentinel_Project
cd /d %PROJECT_ROOT%

echo [SYSTEM] Activating Virtual Environment...
call venv\Scripts\activate

echo [SYSTEM] Launching Sentinel Watchdog Supervisor...
echo [SYSTEM] Monitoring Fast Loop (MT5) and Slow Loop (Oracle Cache)...
echo.

python monitor_sentinel.py

pause
