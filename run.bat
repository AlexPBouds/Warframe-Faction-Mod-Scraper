@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo Creating virtual environment...
py -3 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto setup_error

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto setup_error

:run
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
exit /b 0

:setup_error
echo.
echo Setup failed. Install Python 3.10 or newer, then run this file again.
pause
exit /b 1
