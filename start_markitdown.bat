@echo off
REM ============================================================
REM MarkItDown Website Launcher (Webcom Powered)
REM ============================================================
setlocal
cd /d "%~dp0"

REM 1. Foreground / Debug Mode check
if "%1"=="-d" goto :run_server
if "%1"=="--debug" goto :run_server
if "%1"=="-f" goto :run_server
if "%1"=="--foreground" goto :run_server
if "%1"=="__bg__" goto :run_server

REM 2. By default, start server and open browser
echo ============================================================
echo   Starting MarkItDown Website (Port 8002)...
echo ============================================================

REM Find Python interpreter from Webcom
set "PY="
if exist "%~dp0..\Webcom\python\python.exe" set "PY=%~dp0..\Webcom\python\python.exe"
if not defined PY if exist "C:\Apps\Webcom\python\python.exe" set "PY=C:\Apps\Webcom\python\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
    echo [ERROR] Webcom Python was not found!
    echo Please make sure C:\Apps\Webcom\python\python.exe exists.
    pause
    exit /b 1
)

REM Free port 8002 if occupied
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

REM Launch server in background
if exist "%~dp0..\Webcom\python\pythonw.exe" (
    start "" "%~dp0..\Webcom\python\pythonw.exe" "%~dp0server.py"
) else (
    start /min "MarkItDown Service (Port 8002)" "%PY%" "%~dp0server.py"
)

REM Wait 1.5 seconds for server to start
timeout /t 2 /nobreak >nul

REM Open browser
echo [OK] Opening MarkItDown in browser...
start "" "http://127.0.0.1:8002"

echo ============================================================
echo   MarkItDown is running at http://127.0.0.1:8002
echo ============================================================
exit /b 0

:run_server
REM Foreground execution
set "PY="
if exist "%~dp0..\Webcom\python\python.exe" set "PY=%~dp0..\Webcom\python\python.exe"
if not defined PY if exist "C:\Apps\Webcom\python\python.exe" set "PY=C:\Apps\Webcom\python\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"

"%PY%" "%~dp0server.py"
exit /b %ERRORLEVEL%
