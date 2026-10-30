@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\jarvis.exe" (
    echo JARVIS no esta instalado. Ejecuta primero instalar.bat
    pause
    exit /b 1
)
".venv\Scripts\jarvis.exe" chat
pause
