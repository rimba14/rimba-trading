# START_SENTINEL.ps1 — THE ONE TRUE LAUNCHER
param([switch]$DryRun = $false, [switch]$PaperMode = $false)
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  SENTINEL LAUNCHER — CANONICAL EDITION' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan

# STEP 0: Ruthless Process Purge
Write-Host '[PURGE] Purging all active python processes to prevent zombies...' -ForegroundColor Yellow
taskkill /F /T /IM python.exe 2>$null
Get-Process | Where-Object {$_.Name -eq "python"} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# STEP 0A: Identity Breach Check
$breachFlag = 'C:\Sentinel_Project\IDENTITY_BREACH.flag'
if (Test-Path $breachFlag) {
    Write-Host '[ABORT] IDENTITY BREACH FLAG DETECTED:' -ForegroundColor Red
    Get-Content $breachFlag | Write-Host -ForegroundColor Red
    Write-Host 'Resolve the breach manually, then delete $breachFlag to re-enable launch.' -ForegroundColor Yellow
    exit 1
}

# Set Paper Mode environment variable if requested
if ($PaperMode) {
    $env:SENTINEL_PAPER_MODE = '1'
    Write-Host '[CONTROLLED BURN] Paper Mode requested. Environment variable set.' -ForegroundColor Cyan
} else {
    $env:SENTINEL_PAPER_MODE = '0'
}

# STEP 1: Run Unified Preflight Gate
Write-Host '[PREFLIGHT] Running unified system health gates...' -ForegroundColor Yellow
python C:\Sentinel_Project\canonical_preflight.py
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ABORT] Pre-flight gate failed. See above outputs.' -ForegroundColor Red
    exit 1
}

# STEP 3: Launch services in correct sequence
Write-Host '[LAUNCH] Starting Machine C (Macro Calendar Sync)...' -ForegroundColor Yellow
Start-Process python -ArgumentList 'macro_calendar_sync.py' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Machine D (Risk Agent)...' -ForegroundColor Yellow
Start-Process python -ArgumentList 'agents\risk_agent.py' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Machine E (SRE Watchdog Daemon)...' -ForegroundColor Yellow
Start-Process python -ArgumentList 'sre_watchdog.py' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Machine A (Profit Manager v28.34 - Composite HMM)...' -ForegroundColor Yellow
Start-Process python -ArgumentList 'profit_manager_v28_34.py' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Machine B (FastAPI Sniper)...' -ForegroundColor Yellow
Start-Process python -ArgumentList '-m uvicorn fastapi_sniper:app --host 0.0.0.0 --port 8000' -PassThru
Start-Sleep -Seconds 5

Write-Host '[LAUNCH] Starting Slow Loop...' -ForegroundColor Yellow
Start-Process python -ArgumentList 'sentinel_slow_loop.py' -PassThru

Write-Host '[OK] All services launched successfully under v30.50 (CADES Empirical & Microstructure)!' -ForegroundColor Green
