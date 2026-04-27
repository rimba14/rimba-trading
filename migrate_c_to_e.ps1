# Vantage System Stabilization | C: to E: Migration
$ErrorActionPreference = "Continue"

$baseE = "E:\system_archive"
if (!(Test-Path $baseE)) { New-Item -ItemType Directory -Path $baseE }

# 1. PURGE CLEAR TRASH
Write-Host "[*] Purging legacy installers and temp files..."
Get-ChildItem -Path "C:\Users\Administrator\Downloads" -Filter "*.exe" | Where-Object { $_.Name -like "*LobeHub*" -or $_.Name -like "*installer*" } | Remove-Item -Force
Get-ChildItem -Path "C:\Users\Administrator\Downloads" -Filter "*.tmp" | Remove-Item -Force

# 2. MIGRATE BULK FOLDERS (Move to E:)
$foldersToMove = @(
    "C:\Users\Administrator\Desktop\MWC PICS",
    "C:\Users\Administrator\Desktop\Reports 2025",
    "C:\Users\Administrator\Desktop\books 2"
)

foreach ($folder in $foldersToMove) {
    if (Test-Path $folder) {
        $dest = Join-Path $baseE (Split-Path $folder -Leaf)
        Write-Host "[*] Migrating: $folder -> $dest"
        Move-Item -Path $folder -Destination $dest -Force
    }
}

Write-Host "[DONE] Migration complete. Verifying system headroom..."
Get-PSDrive C | Select-Object Name, @{Name="Free(GB)";Expression={[math]::round($_.Free/1GB,2)}}
