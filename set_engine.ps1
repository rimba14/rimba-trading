param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("LOCAL", "GROQ", "GEMINI", "AUTO")]
    [string]$Engine
)

Write-Host "--- SENTINEL ENGINE SWITCHBOARD ---" -ForegroundColor Cyan
if ($Engine -eq "AUTO") {
    [System.Environment]::SetEnvironmentVariable('SENTINEL_ENGINE', $null, 'User')
    $env:SENTINEL_ENGINE = $null
    Write-Host "Mode set to: AUTO-ROUTER (Dynamic Logic Active)" -ForegroundColor Green
} else {
    [System.Environment]::SetEnvironmentVariable('SENTINEL_ENGINE', $Engine, 'User')
    $env:SENTINEL_ENGINE = $Engine
    Write-Host "Mode set to: $Engine (Manual Override Active)" -ForegroundColor Green
}
Write-Host "Restart Sentinel or the background loop to apply changes." -ForegroundColor Yellow
