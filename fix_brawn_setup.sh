#!/bin/bash
# fix_brawn_setup.sh - Finalizing Python and MT5 staging

set -e

# 1. Install xvfb (Virtual Frame Buffer) if missing
apt-get update
apt-get install -y xvfb

# 2. Re-attempt Python Silent Install with xvfb-run
echo "Downloading Windows Python 3.10.11..."
wget -q https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe -O /tmp/python_installer.exe

echo "Executing Silent Python Install via xvfb-run and WINE..."
# xvfb-run provides a virtual X server to satisfy WINE's window creation requirements
su - ubuntu -c "xvfb-run -a wine /tmp/python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1"

# 3. Re-attempt MT5 Pre-Staging
echo "Pre-staging MetaTrader 5 Setup..."
mkdir -p /home/ubuntu/Desktop
wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /home/ubuntu/Desktop/mt5setup.exe
chown -R ubuntu:ubuntu /home/ubuntu/Desktop

echo "--- [SUCCESS] Setup Finalized. ---"
