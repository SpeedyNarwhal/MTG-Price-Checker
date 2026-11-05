$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "Building frontend..."
Push-Location web\frontend
npm install
npm run build
if (-not (Test-Path "dist\index.html")) {
    throw "Frontend build missing dist\index.html"
}
Pop-Location

Write-Host "Installing packaging deps..."
python -m pip install -e ".[desktop,browser]"
python -m pip install "pyinstaller>=6.0"

Write-Host "Building executable..."
python -m PyInstaller --noconfirm --clean mtg_price_checker.spec

$exe = Join-Path (Get-Location) "dist\MTG-Price-Checker.exe"
if (-not (Test-Path $exe)) {
    throw "Expected exe not found: $exe"
}

Write-Host "Done: $exe"
