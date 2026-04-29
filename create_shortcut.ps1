$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\Sentinel Bridge.lnk")
$Shortcut.TargetPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$Shortcut.Arguments = '-ExecutionPolicy Bypass -WindowStyle Normal -File "C:\Sentinel_Project\Start-Sentinel-Tunnel.ps1"'
$Shortcut.Description = "Persistent SSH Tunnel for Sentinel Execution Node"
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll, 247"
$Shortcut.Save()
Write-Host "Shortcut created successfully at $DesktopPath\Sentinel Bridge.lnk"
