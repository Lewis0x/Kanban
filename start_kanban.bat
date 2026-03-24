@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"

where python >nul 2>&1
if errorlevel 1 goto :ErrNoPython

if exist ".venv\Scripts\python.exe" goto :HaveVenv
echo Creating virtual environment .venv ...
python -m venv .venv
if errorlevel 1 goto :ErrVenv
:HaveVenv

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :ErrPip

echo.
echo ========================================
echo   Kanban started
echo   Open: http://127.0.0.1:5000
echo   Press Ctrl+C to stop
echo ========================================
echo.

set "PYTHONPATH=%ROOT%"
".venv\Scripts\python.exe" -m flask --app app.main run --debug

echo.
pause
goto :EOF

:ErrNoPython
echo [ERROR] Python not found. Install Python 3 and add it to PATH.
pause
exit /b 1

:ErrVenv
echo [ERROR] Failed to create .venv
pause
exit /b 1

:ErrPip
echo [ERROR] pip install failed.
pause
exit /b 1
