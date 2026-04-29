#!/bin/bash

# Project "Institutional Brawn" Deployment Script
# Purpose: Launch MT5 and Execution Nodes on headless Linux via WINE/Xvfb.

# 1. Environment Check
if ! command -v xvfb-run &> /dev/null; then
    echo "[ERROR] xvfb-run not found. Install with: sudo apt install xvfb"
    exit 1
fi

if ! command -v wine &> /dev/null; then
    echo "[ERROR] wine not found. Please install wine-stable."
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[SYSTEM] Launching Execution Nodes from $PROJECT_DIR"

# 2. Kill existing processes to prevent lock collisions
pkill -f "vantage_execute.py"
pkill -f "profit_manager.py"
pkill -f "terminal64.exe"

# 3. Launch MetaTrader 5 (Headless)
# Adjust the path to your terminal64.exe inside the WINE prefix
MT5_PATH="$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe"
if [ -f "$MT5_PATH" ]; then
    echo "[SYSTEM] Booting MT5..."
    xvfb-run -a wine "$MT5_PATH" /portable &
    sleep 10
else
    echo "[WARNING] Could not find MT5 at $MT5_PATH. Ensure it is installed in the WINE prefix."
fi

# 4. Launch Execution Layer Scripts
echo "[SYSTEM] Starting Vantage Execute (Discord Bridge)..."
xvfb-run -a wine python "$PROJECT_DIR/vantage_execute.py" &

sleep 5

echo "[SYSTEM] Starting Profit Manager (Virtual Seatbelt)..."
xvfb-run -a wine python "$PROJECT_DIR/profit_manager.py" &

echo "[SUCCESS] Project 'Institutional Brawn' is online."
echo "Use 'tail -f vantage_execute_brawn.log' to monitor."
