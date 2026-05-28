$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Output "Step 0: Ruthless Process Purge"
taskkill /F /T /IM python.exe 2>$null
Get-Process | Where-Object {$_.Name -eq "python"} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Output "Step 1: Igniting Macro Calendar Sync"
$p_macro = Start-Process python -ArgumentList "macro_calendar_sync.py" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Output "Step 2: Igniting Risk Agent"
$p_risk = Start-Process python -ArgumentList "agents/risk_agent.py" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Output "Step 3: Igniting SRE Watchdog Daemon"
$p_sre = Start-Process python -ArgumentList "sre_watchdog.py" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Output "Step 4: Igniting Profit Manager v25.0"
$p_profit = Start-Process python -ArgumentList "profit_manager_v28_34.py" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Output "Step 5: Igniting Execution Bridge (FastAPI Sniper)"
$p_fastapi = Start-Process python -ArgumentList "-m uvicorn fastapi_sniper:app --host 0.0.0.0 --port 8000" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5

Write-Output "Checking Port 8000 and 8001 Bind..."
netstat -ano | findstr :8000
netstat -ano | findstr :8001

Write-Output "Step 6: Igniting Alpha Factory (Slow Loop)"
$p_slow = Start-Process python -ArgumentList "sentinel_slow_loop.py" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Output ""
Write-Output "=== PIDs ==="
Write-Output "macro_calendar_sync.py : $($p_macro.Id)"
Write-Output "risk_agent.py          : $($p_risk.Id)"
Write-Output "sre_watchdog.py        : $($p_sre.Id)"
Write-Output "profit_manager_v28_34.py  : $($p_profit.Id)"
Write-Output "fastapi_sniper.py      : $($p_fastapi.Id)"
Write-Output "sentinel_slow_loop.py  : $($p_slow.Id)"
Write-Output "============"

Write-Output ""
Write-Output "Checking MT5 Equity..."
python -c "import MetaTrader5 as mt5; mt5.initialize(); acc=mt5.account_info(); print(f'LIVE EQUITY: {acc.equity} USD' if acc else 'LIVE EQUITY: MT5 Connection Failed'); mt5.shutdown()"
