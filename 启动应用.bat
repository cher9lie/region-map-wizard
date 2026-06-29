@echo off
cd /d "%~dp0"
echo Starting Region Map Wizard...
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: venv not found
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m src.main
if errorlevel 1 (
    echo.
    echo Application exited with error.
    pause
)
