@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 "tools\reorder_boot_disk.py"
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Python 3 not found. Use the same Python installation already used for Recovery.
  ) else (
    python "tools\reorder_boot_disk.py"
  )
)
pause
