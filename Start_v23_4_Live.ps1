# Start_v23_4_Live.ps1
# Comprehensive Sentinel v23.4 Startup

$PROJECT_ROOT = "C:\Sentinel_Project"
Set-Location $PROJECT_ROOT

Write-Host "##########################################################" -ForegroundColor Cyan
Write-Host "  ADAPTIVE SENTINEL v23.4 - LIVE RESUMPTION"           -ForegroundColor Cyan
Write-Host "##########################################################" -ForegroundColor Cyan

# 1. MT5 Check
Write-Host "[1/5] Ensuring MetaTrader 5 is running..." -ForegroundColor Yellow
$mt5 = Get-Process terminal64 -ErrorAction SilentlyContinue
if (-not $mt5) {
    Start-Process "C:\Program Files\MetaTrader 5\terminal64.exe"
    Start-Sleep -Seconds 10
}
Write-Host "[OK] MT5 Active." -ForegroundColor Green

# 2. Start Risk Agent (Port 8001)
Write-Host "[2/5] Launching Risk Agent (Port 8001)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe agents\risk_agent.py" -WindowStyle Normal

# 3. Start Execution Node (FastAPI Sniper - Port 8000)
Write-Host "[3/5] Launching Execution Node (FastAPI Sniper)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe fastapi_sniper.py" -WindowStyle Normal

# 4. Start Profit Manager (Exit Guard)
Write-Host "[4/5] Launching Profit Manager..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe profit_manager.py" -WindowStyle Normal

# 5. Start Oxford Orchestrator (Slow Loop)
Write-Host "[5/5] Launching Oxford Orchestrator (Slow Loop)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe oxford_orchestrator.py" -WindowStyle Normal

Write-Host ""
Write-Host "[SUCCESS] Sentinel v23.4 Pipeline is LIVE." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
