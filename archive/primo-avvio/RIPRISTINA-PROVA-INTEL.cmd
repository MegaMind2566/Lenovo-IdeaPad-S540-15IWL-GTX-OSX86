@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "tools\recovery_runtime_logs.py" --restore
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Python 3 non trovato. Usa lo stesso Python gia usato per la Recovery.
  ) else (
    python "tools\recovery_runtime_logs.py" --restore
  )
)
pause
