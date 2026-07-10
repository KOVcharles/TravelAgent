@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Hommey 商旅助手 - Docker 模式
echo ============================================
echo.
echo [1] WebUI 模式 (http://localhost:8000^)
echo [2] CLI 交互模式
echo [3] 构建镜像
echo [4] 停止并清理
echo.

set /p choice="请选择 (1/2/3/4): "

if "%choice%"=="1" (
    echo.
    echo 正在启动 WebUI 模式...
    docker compose -f docker\docker-compose.yml up -d
    echo.
    echo WebUI 已启动: http://localhost:8000
    echo 查看日志: docker compose -f docker\docker-compose.yml logs -f
)

if "%choice%"=="2" (
    echo.
    echo 正在启动 CLI 交互模式...
    docker compose -f docker\docker-compose.yml run --rm hommey python cli.py
)

if "%choice%"=="3" (
    echo.
    echo 正在构建 Docker 镜像...
    docker compose -f docker\docker-compose.yml build
)

if "%choice%"=="4" (
    echo.
    echo 正在停止容器...
    docker compose -f docker\docker-compose.yml down
)

pause
