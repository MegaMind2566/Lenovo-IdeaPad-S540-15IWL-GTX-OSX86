@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "tools\trace_intel.py" --recover
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Python 3 not found. Use the same Python already used for Recovery.
  ) else (
    python "tools\trace_intel.py" --recover
  )
)
pause
