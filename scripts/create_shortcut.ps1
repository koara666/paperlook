# Creates a "PaperLook" shortcut (default: on the Desktop) that starts the app with one double-click.
param([string]$Destination = [Environment]::GetFolderPath('Desktop'))

$root = Split-Path -Parent $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $Destination 'PaperLook.lnk'))
$lnk.TargetPath = Join-Path $root 'start.bat'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = Join-Path $root 'assets\paperlook.ico'
$lnk.WindowStyle = 7   # start minimised: the console stays in the taskbar, the browser opens
$lnk.Description = 'PaperLook - daily papers'
$lnk.Save()
Write-Output "Shortcut created: $(Join-Path $Destination 'PaperLook.lnk')"
