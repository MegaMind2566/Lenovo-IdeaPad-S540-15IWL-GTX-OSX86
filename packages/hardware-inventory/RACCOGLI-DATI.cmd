@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0tools\Raccogli-Dati.ps1" (
    echo Estrai tutto lo ZIP prima di avviare il programma.
    pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Raccogli-Dati.ps1"
if errorlevel 1 (
    echo.
    echo Raccolta non completata. Leggi il messaggio sopra.
    echo Se presente, allega errore-avvio.txt nella chat.
    pause
)
endlocal
