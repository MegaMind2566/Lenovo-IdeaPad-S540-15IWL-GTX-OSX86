@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
  set "S540_PY_CMD=py -3"
) else (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Installa Python 3 da https://www.python.org/downloads/windows/ e riprova.
    pause
    exit /b 1
  )
  set "S540_PY_CMD=python"
)
%S540_PY_CMD% "tools\macrecovery\macrecovery.py" -b Mac-5F9802EFE386AA28 -m 00000000000000000 -os latest download
if errorlevel 1 (
  echo Download non completato. Non copiare file incompleti sulla chiavetta.
) else (
  echo Recovery scaricata. Segui LEGGIMI.md per copiarla sulla chiavetta.
)
pause
