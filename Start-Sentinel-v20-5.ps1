# Start-Sentinel-v20-5.ps1
# Adaptive Sentinel v20.5 System Startup
# Objective: Launch the full Information-Driven matrix in the correct order.

Write-Host "##########################################################" -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  ADAPTIVE SENTINEL - OPERATION PHOENIX (v20.5)"        -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "#          Phase 1-6 Architecture Online                 #" -ForegroundColor Cyan
Write-Host "#                                                        #" -ForegroundColor Cyan
Write-Host "##########################################################" -ForegroundColor Cyan
Write-Host ""

$PROJECT_ROOT = "C:\Sentinel_Project"
Set-Location $PROJECT_ROOT

# 1. MT5 Initialization
Write-Host "[SYSTEM] Checking for MetaTrader 5..." -ForegroundColor Yellow
$mt5Process = Get-Process terminal64 -ErrorAction SilentlyContinue
if ($mt5Process) {
    Write-Host "[OK] MetaTrader 5 is already running." -ForegroundColor Green
} else {
    Write-Host "[SYSTEM] Launching MetaTrader 5..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\MetaTrader 5\terminal64.exe"
    Start-Sleep -Seconds 10
}

# 2. Virtual Environment Activation & Cleanup
Write-Host "[SYSTEM] Cleaning existing Sentinel processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "sentinel" -or $_.CommandLine -match "fastapi" -or $_.CommandLine -match "profit" } | Stop-Process -Force
Start-Sleep -Seconds 2

# 3. Launch Execution Node (Machine B)
Write-Host "[SYSTEM] Starting Execution Node (FastAPI Sniper)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe fastapi_sniper.py" -WindowStyle Normal

# 4. Launch Profit Manager
Write-Host "[SYSTEM] Starting Thesis-Driven Profit Manager..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe profit_manager.py" -WindowStyle Normal

# 5. Launch Deep Research Daemon (The Macro Daemon)
Write-Host "[SYSTEM] Starting Deep Research Oracle (24h Loop)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe sentinel_deep_research.py" -WindowStyle Normal

# 6. Launch Continuous Retrainer
Write-Host "[SYSTEM] Starting Continuous Retraining Daemon..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe sentinel_retrainer.py" -WindowStyle Normal

# 7. Launch Slow Loop (Cognition Engine)
Write-Host "[SYSTEM] Starting Cognitive Engine (Slow Loop)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe sentinel_slow_loop.py" -WindowStyle Normal

Write-Host ""
Write-Host "[SUCCESS] Adaptive Sentinel v20.4 Matrix is fully online." -ForegroundColor Green
Write-Host "System status can be monitored via the spawned console windows." -ForegroundColor Gray
Write-Host ""
