@echo off
REM ============================================================
REM MarkItDown Website - Stop Service (Port 8002)
REM ============================================================
setlocal
cd /d "%~dp0"

echo Stopping MarkItDown Service (Port 8002)...

powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [OK] MarkItDown Service (Port 8002) has been stopped.
timeout /t 2 /nobreak >nul
exit /b 0
