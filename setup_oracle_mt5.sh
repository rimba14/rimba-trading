#!/bin/bash
# setup_oracle_mt5.sh - Automated VPS Provisioning for Institutional Brawn
# Directive 1: Master Setup Script (Non-interactive)

set -e 

# Ensure non-interactive mode for apt
export DEBIAN_FRONTEND=noninteractive

# 1. Swap File (CRITICAL for 1GB RAM)
echo "[1/5] Creating 4GB Swap File..."
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap file created and activated."
else
    echo "Swap file already exists. Skipping."
fi

# 2. GUI & RDP Setup
echo "[2/5] Installing XFCE4 and XRDP..."
apt-get update
apt-get install -y xfce4 xfce4-goodies xrdp
echo "xfce4-session" > /home/ubuntu/.xsession
chown ubuntu:ubuntu /home/ubuntu/.xsession
systemctl enable xrdp
systemctl restart xrdp
# Open RDP port in UFW (if enabled)
if command -v ufw > /dev/null; then
    ufw allow 3389
fi

# 3. WINE Installation
echo "[3/5] Installing WINE Stack..."
dpkg --add-architecture i386
apt-get update
apt-get install -y wine64 wine32 winbind winetricks

# 4. Windows Python Download & Silent Install
echo "[4/5] Downloading Windows Python 3.10.11..."
wget -q https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe -O /tmp/python_installer.exe

echo "Executing Silent Python Install via WINE..."
# We run as ubuntu user to initialize the wineprefix
# /quiet: No UI, InstallAllUsers=1: System-wide, PrependPath=1: Add to PATH
su - ubuntu -c "wine /tmp/python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1"

# 5. MT5 Pre-Staging
echo "[5/5] Pre-staging MetaTrader 5 Setup..."
mkdir -p /home/ubuntu/Desktop
wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O /home/ubuntu/Desktop/mt5setup.exe
chown -R ubuntu:ubuntu /home/ubuntu/Desktop

echo "--- [SUCCESS] Project 'One-Click Oracle Brawn' Provisioning Complete. ---"
echo "--- Connect to 165.1.77.111 via RDP on port 3389 (User: ubuntu) ---"
