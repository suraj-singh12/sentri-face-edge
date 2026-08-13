$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "=== SentriFace Edge Release Build ==="
Write-Host ""

Write-Host "[1/4] Cleaning previous build..."
if (Test-Path ".\build") {
    Remove-Item ".\build" -Recurse -Force
}

Write-Host "[2/4] Building frontend..."
Push-Location ".\frontend"
npm run build
Pop-Location

Write-Host "[3/4] Building Windows executable with Nuitka..."

python -m nuitka `
--mode=standalone `
--output-dir=build `
--output-filename=SentriFaceEdge.exe `
--windows-icon-from-ico=packaging\windows\SentriFaceEdge.ico `
--windows-console-mode=disable `
--include-package=sentriface `
--include-data-dir=src\sentriface\ui_static=sentriface\ui_static `
--include-data-dir=packaging\runtime\core=runtime\core `
src\sentriface\ui.py

Write-Host "[4/4] Building installer..."

& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" `
".\installer\SentriFaceEdge.iss"

Write-Host ""
Write-Host "===================================="
Write-Host "BUILD COMPLETE"
Write-Host "Installer location:"
Write-Host "$Root\installer_output"
Write-Host "===================================="