@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "tools\test_bluetooth.py" --restore
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Python 3 not found. Use the same Python installation used to download Recovery.
  ) else (
    python "tools\test_bluetooth.py" --restore
  )
)
pause
