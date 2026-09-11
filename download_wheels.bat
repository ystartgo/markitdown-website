@echo off
REM ============================================================
REM MarkItDown Website - Download Pyodide & Wheels Runtime
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Downloading Pyodide runtime and Python wheels (~400MB)
echo ============================================================

set "PY="
if exist "%~dp0..\Webcom\python\python.exe" set "PY=%~dp0..\Webcom\python\python.exe"
if not defined PY if exist "C:\Apps\Webcom\python\python.exe" set "PY=C:\Apps\Webcom\python\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
    echo [ERROR] Webcom Python was not found!
    echo Please ensure C:\Apps\Webcom\python\python.exe exists.
    pause
    exit /b 1
)

"%PY%" "%~dp0scripts\download_wheels.py"

echo.
pause
