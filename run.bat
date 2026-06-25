@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set NO_PROXY=*
set no_proxy=*
cd /d "%~dp0"

REM 如果有虚拟环境则自动激活
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python cli.py %*
if %errorlevel% neq 0 (
    echo.
    echo 按任意键退出...
    pause >nul
)
