@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=*
set no_proxy=*
cd /d "%~dp0"
python cli.py %*
if %errorlevel% neq 0 (
    echo.
    echo 按任意键退出...
    pause >nul
)
