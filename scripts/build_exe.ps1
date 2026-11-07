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
$exe = Join-Path (Get-Location) "dist\MTG-Price-Checker.exe"
$beforeWriteTime = $null
if (Test-Path $exe) {
    $beforeWriteTime = (Get-Item $exe).LastWriteTimeUtc
    $locked = Get-Process | Where-Object {
        try { $_.Path -eq $exe } catch { $false }
    }
    if ($locked) {
        $ids = ($locked | ForEach-Object { $_.Id }) -join ", "
        throw "Close MTG-Price-Checker.exe before rebuilding (PID(s): $ids). The previous rebuild failed because the file was locked."
    }
}

python -m PyInstaller --noconfirm --clean mtg_price_checker.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $exe)) {
    throw "Expected exe not found: $exe"
}

$afterWriteTime = (Get-Item $exe).LastWriteTimeUtc
if ($beforeWriteTime -ne $null -and $afterWriteTime -le $beforeWriteTime) {
    throw "Exe was not updated (still $afterWriteTime). Close any running copy and rebuild."
}

Write-Host "Done: $exe ($((Get-Item $exe).Length) bytes, written $afterWriteTime UTC)"
