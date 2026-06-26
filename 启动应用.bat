@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 Region Map Wizard...
if not exist ".venv\Scripts\python.exe" (
    echo 错误: 找不到虚拟环境，请先运行 scripts\setup_env.bat
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m src.main
if errorlevel 1 (
    echo.
    echo 程序异常退出，错误码: %errorlevel%
    pause
)
