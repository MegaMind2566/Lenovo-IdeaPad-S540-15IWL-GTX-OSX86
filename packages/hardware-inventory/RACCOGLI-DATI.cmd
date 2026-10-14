@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0tools\Raccogli-Dati.ps1" (
    echo Extract the complete ZIP before running the program.
    pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Raccogli-Dati.ps1"
if errorlevel 1 (
    echo.
    echo Collection did not complete. Read the message above.
    echo If available, attach errore-avvio.txt in the chat.
    pause
)
endlocal
