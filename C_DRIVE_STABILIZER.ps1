# EMERGENCY C: DRIVE STABILIZER
$ErrorActionPreference = "SilentlyContinue"

Write-Host "[*] Initiating Deep Purge of C: Drive..."
$initialFree = [math]::round((Get-PSDrive C).Free / 1GB, 2)

# 1. Purge Temp Directories
$tempPaths = @(
    "C:\Windows\Temp\*",
    "C:\Users\Administrator\AppData\Local\Temp\*",
    "C:\Users\Administrator\AppData\Local\Microsoft\Windows\INetCache\*",
    "C:\Users\Administrator\AppData\Local\Google\Chrome\User Data\Default\Cache\*"
)

foreach ($path in $tempPaths) {
    Write-Host "[*] Clearing: $path"
    Remove-Item -Path $path -Recurse -Force
}

# 2. Cleanup Windows Update Cache (if possible)
Write-Host "[*] Clearing SoftwareDistribution cache..."
Stop-Service -Name "wuauserv" 
Remove-Item -Path "C:\Windows\SoftwareDistribution\Download\*" -Recurse -Force
Start-Service -Name "wuauserv"

$finalFree = [math]::round((Get-PSDrive C).Free / 1GB, 2)
$recovered = [math]::round($finalFree - $initialFree, 2)

Write-Host "`n[SUCCESS] Stabilization Complete."
Write-Host "Initial Free: $initialFree GB"
Write-Host "Final Free:   $finalFree GB"
Write-Host "Recovered:    $recovered GB"
