@echo off
REM HALUNG Clip Control — Windows Installation

setlocal
cd /d "%~dp0"

echo ========================================
echo HALUNG Clip Control V12 - Installation
echo ========================================
echo.

REM Create virtual environment
echo Creating Python virtual environment...
py -3 -m venv .venv
if errorlevel 1 (
    echo Failed to create venv with py -3, trying python...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install requirements
echo Installing dependencies...
pip install -r requirements.txt

if errorlevel 1 (
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Installation complete!
echo.
echo To start the Dashboard:
echo   run_pc.bat
echo.
echo Or manually:
echo   .venv\Scripts\activate.bat
echo   python dashboard/app.py
echo ========================================
pause
