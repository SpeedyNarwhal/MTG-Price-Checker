@echo off
setlocal
cd /d "%~dp0"

if not exist "web\frontend\dist\index.html" (
  echo Building frontend...
  pushd web\frontend
  call npm install
  if errorlevel 1 exit /b 1
  call npm run build
  if errorlevel 1 exit /b 1
  popd
)

python -m mtg_price_checker.desktop
endlocal
