@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY if exist "C:\Users\18271\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PY=C:\Users\18271\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PY set "PY=python"

echo ============================================================
echo   Image Workbench - starting
echo   Python: %PY%
echo ============================================================

"%PY%" bootstrap.py
if errorlevel 1 goto fail

"%PY%" app.py
goto end

:fail
echo.
echo [ERROR] bootstrap failed. Check python path or run: python bootstrap.py

:end
echo.
pause
