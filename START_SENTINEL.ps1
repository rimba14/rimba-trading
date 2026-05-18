# START_SENTINEL.ps1 — THE ONE TRUE LAUNCHER
param([switch]$DryRun = $false, [switch]$PaperMode = $false)
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  SENTINEL LAUNCHER — CANONICAL EDITION' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan

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
Write-Host '[LAUNCH] Starting Machine A (Profit Manager)...' -ForegroundColor Yellow
Start-Process .\venv\Scripts\python.exe -ArgumentList 'profit_manager.py' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Machine B (FastAPI Sniper)...' -ForegroundColor Yellow
Start-Process .\venv\Scripts\python.exe -ArgumentList '-m uvicorn fastapi_sniper:app --host 0.0.0.0 --port 8000' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Machine C (Risk Agent)...' -ForegroundColor Yellow
Start-Process .\venv\Scripts\python.exe -ArgumentList 'agents\risk_agent.py' -PassThru
Start-Sleep -Seconds 3

Write-Host '[LAUNCH] Starting Slow Loop...' -ForegroundColor Yellow
Start-Process .\venv\Scripts\python.exe -ArgumentList 'sentinel_slow_loop.py' -PassThru

Write-Host '[OK] All services launched successfully under v28.12!' -ForegroundColor Green
