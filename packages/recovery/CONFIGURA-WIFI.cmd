@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "tools\configure_wifi.py"
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Installa Python 3 da https://www.python.org/downloads/windows/ e riprova.
  ) else (
    python "tools\configure_wifi.py"
  )
)
pause
