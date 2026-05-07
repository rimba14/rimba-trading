# Start-Sentinel-v21-0.ps1
# Adaptive Sentinel v21.0 System Startup
# Objective: Launch the full Information-Driven matrix in the correct order.
# v21.0 Changes:
#   - UTF-8 console encoding to prevent UnicodeEncodeError in slow loop
#   - PYTHONUTF8=1 propagated to all python subprocesses
#   - Ollama health-check gate before launching slow loop

Write-Host "##########################################################" -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  ADAPTIVE SENTINEL - ALPHA ENGINEERING (v21.0)"       -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "#          Phase 1-6 Architecture Online                 #" -ForegroundColor Cyan
Write-Host "#   SRE Patch: UTF-8 Encoding + Ollama Health Gate       #" -ForegroundColor Cyan
Write-Host "##########################################################" -ForegroundColor Cyan
Write-Host ""

# --- SRE PATCH v21.0: Force UTF-8 console encoding ---
# Prevents UnicodeEncodeError on Windows CP-1252 consoles (slow_loop_stderr bug)
chcp 65001 | Out-Null
$env:PYTHONUTF8 = "1"
Write-Host "[SRE] Console encoding set to UTF-8 (CP65001)." -ForegroundColor DarkGray

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

# 7. Ollama Health Check (v21.0 Gate)
# MoE uses cloud routing as primary; Ollama is optional.
# This gate warns if Ollama is unreachable so the 10s/asset timeout can be anticipated.
Write-Host "[SRE] Checking local Ollama server health..." -ForegroundColor DarkGray
try {
    $ollamaResp = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] Ollama is reachable. Local MoE available as secondary path." -ForegroundColor Green
} catch {
    Write-Host "[WARN] Ollama unreachable at 127.0.0.1:11434. MoE will route via cloud (Math Meta-Model)." -ForegroundColor Yellow
    Write-Host "[WARN] Expect 10s timeout per asset if Ollama fallback fires. Consider starting Ollama." -ForegroundColor Yellow
}

# 8. Launch Slow Loop (Cognition Engine)
Write-Host "[SYSTEM] Starting Cognitive Engine (Slow Loop)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe sentinel_slow_loop.py" -WindowStyle Normal

Write-Host ""
Write-Host "[SUCCESS] Adaptive Sentinel v21.0 Matrix is fully online." -ForegroundColor Green
Write-Host "System status can be monitored via the spawned console windows." -ForegroundColor Gray
Write-Host ""
