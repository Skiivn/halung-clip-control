@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Virtual environment not found. Running install_windows.bat...
    call install_windows.bat
)

call .venv\Scripts\activate.bat

echo Starting HALUNG Dashboard...
echo.
python dashboard/app.py

endlocal
