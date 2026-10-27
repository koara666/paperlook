# Build the Windows desktop app (run from any directory, in Windows PowerShell or pwsh):
#   python -m pip install -r requirements-desktop.txt
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-Python python] [-SmokeTest]
# Output in dist\:
#   PaperLook\                               the app folder (PaperLook.exe + _internal\)
#   PaperLook-<version>-Windows-Portable.zip that folder zipped
#   PaperLook-<version>-Windows-Setup.exe    installer (only when Inno Setup 6/7 is installed)
param(
    [string]$Python = "python",
    [switch]$SmokeTest
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONUTF8 = "1"

# Native tools log to stderr; Windows PowerShell 5.1 would turn that into terminating errors under
# "Stop", so run them with "Continue" and judge success by the exit code only.
function Invoke-Native([string]$Exe, [string[]]$Arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } | Out-Host } finally { $ErrorActionPreference = $old }
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed (exit code $LASTEXITCODE)" }
}

$version = (Select-String -Path "backend\paperlook\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "PaperLook $version"
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

Invoke-Native $Python @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist", "--workpath", "build\pyinstaller", "packaging\paperlook.spec")
$exe = Join-Path $root "dist\PaperLook\PaperLook.exe"

if ($SmokeTest) {
    # Start the packaged app on a throw-away data directory and check that the server answers.
    $data = Join-Path ([IO.Path]::GetTempPath()) ("paperlook-smoke-" + [guid]::NewGuid())
    $env:PAPERLOOK_DATA_DIR = $data
    $env:PAPERLOOK_DISABLE_KEYRING = "1"
    $proc = Start-Process -FilePath $exe -PassThru
    $ok = $false
    for ($i = 0; $i -lt 90 -and -not $ok; $i++) {
        Start-Sleep -Seconds 2
        try {
            $st = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/status" -TimeoutSec 3
            $ok = ($st.packaged -eq $true) -and ($st.version -eq $version)
        } catch { }
    }
    try { $html = (Invoke-WebRequest -Uri "http://127.0.0.1:8765/" -UseBasicParsing -TimeoutSec 5).Content } catch { $html = "" }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item Env:PAPERLOOK_DATA_DIR, Env:PAPERLOOK_DISABLE_KEYRING
    if (-not $ok -or $html -notmatch 'id="root"') {
        Get-Content (Join-Path $data "logs\paperlook.log") -ErrorAction SilentlyContinue | Select-Object -Last 40
        throw "Smoke test failed: the packaged app did not start"
    }
    Write-Host "Smoke test passed"
}

$zip = "dist\PaperLook-$version-Windows-Portable.zip"
Compress-Archive -Path "dist\PaperLook" -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created $zip"

$iscc = Get-ChildItem -Path "$env:ProgramFiles\Inno Setup*\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup*\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup*\ISCC.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $iscc) {
    Write-Warning "Inno Setup not found: installer skipped (https://jrsoftware.org/isdl.php)"
    exit 0
}
$lang = Get-ChildItem -Path (Join-Path $iscc.DirectoryName "Languages") -Recurse -Filter "ChineseSimplified*.isl" -ErrorAction SilentlyContinue | Select-Object -First 1
$defines = @("/DAppVersion=$version")
if ($lang) { $defines += "/DLangFile=$($lang.FullName)" } else { Write-Warning "Simplified Chinese messages not found; installer will be in English" }
Invoke-Native $iscc.FullName ($defines + @("packaging\installer.iss"))
Get-ChildItem dist -File | ForEach-Object { "{0,-50} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }
