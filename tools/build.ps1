# Build dist\unidesk-setup-<version>.exe
#   powershell -ExecutionPolicy Bypass -File tools\build.ps1
# Needs: Python 3.12 with requirements.txt + pyinstaller, .NET 9 SDK, Inno Setup 6.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$version = (Select-String -Path unidesk\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "unidesk $version"

Write-Host "1/5 fonts + icon"
python tools\build_fonts.py
python tools\make_icon.py

Write-Host "2/5 media bridge (self-contained, no .NET needed on the target PC)"
Remove-Item -Recurse -Force build\media-bridge -ErrorAction SilentlyContinue
dotnet publish media-bridge -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=none `
    -o build\media-bridge --nologo -v q
if ($LASTEXITCODE) { throw "media bridge build failed" }

Write-Host "3/5 UI Automation bindings (used for dock badges)"
python -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"

Write-Host "4/5 PyInstaller"
Remove-Item -Recurse -Force dist\unidesk -ErrorAction SilentlyContinue
python -m PyInstaller unidesk.spec --noconfirm --clean --log-level WARN
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Write-Host "5/5 installer"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }
& $iscc /Q "/DAppVersion=$version" installer\unidesk.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }

$setup = Get-Item "dist\unidesk-setup-$version.exe"
Write-Host ("done: {0} ({1:N1} MB)" -f $setup.FullName, ($setup.Length / 1MB))
