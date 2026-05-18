# Start-Sentinel-Tunnel.ps1
# Indestructible SSH Tunnel to Oracle Execution Node
# Directive 2: Client-Side Resilience

while ($true) {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "   SENTINEL INDESTRUCTIBLE TUNNEL ACTIVE" -ForegroundColor Cyan
    Write-Host "   Target: 165.1.77.111 | Port: 3390 -> 3389" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Establishing connection..." -ForegroundColor Green
    
    # Execute SSH with keep-alives and port forwarding
    # -L 3390:localhost:3389 maps remote MT5/RDP to local port 3390
    # -o ExitOnForwardFailure=yes ensures the loop catches bind errors
    ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes -o ExitOnForwardFailure=yes -i "C:\Users\ADMIN\Documents\Oracle key\ssh-key-2026-04-28.key" -L 3390:localhost:3389 ubuntu@165.1.77.111
    
    Write-Host ""
    Write-Host "[WARNING] Tunnel dropped or connection failed." -ForegroundColor Red
    Write-Host "Attempting automatic reconnection in 3 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}
