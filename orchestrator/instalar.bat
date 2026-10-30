@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo ===============================
echo    Instalando JARVIS
echo ===============================
echo.

rem --- 1. Buscar Python 3.11+ ------------------------------------------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [XX] No encontre Python 3.11 o superior.
    echo      Descargalo de https://www.python.org/downloads/
    echo      Al instalar, marca la casilla "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
echo [OK] Python encontrado

rem --- 2. Entorno virtual -----------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [..] Creando entorno virtual...
    %PY% -m venv .venv || goto :error
)
echo [OK] Entorno virtual listo

rem --- 3. Dependencias ---------------------------------------------------
echo [..] Instalando dependencias (puede tardar un par de minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q || goto :error
".venv\Scripts\python.exe" -m pip install -e . -q || goto :error
echo [OK] Dependencias instaladas

rem --- 4. Configuracion ---------------------------------------------------
".venv\Scripts\jarvis.exe" setup || goto :error

echo.
echo Para hablar con JARVIS haz doble clic en  iniciar.bat
echo.
pause
exit /b 0

:error
echo.
echo [XX] Algo fallo. Copia el mensaje de arriba y revisalo.
pause
exit /b 1
