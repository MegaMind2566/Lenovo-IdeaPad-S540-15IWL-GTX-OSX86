@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "tools\test_safe_boot.py" --intel
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Python 3 non trovato. Usa lo stesso Python usato per scaricare la Recovery.
  ) else (
    python "tools\test_safe_boot.py" --intel
  )
)
pause
