@echo off
chcp 65001 >nul
echo ============================================
echo   企业代码智能助手 - 前端开发服务器
echo ============================================
echo.

cd /d "%~dp0"

echo [INFO] 检查依赖...
if not exist "node_modules" (
    echo [INFO] 正在安装依赖...
    npm install --no-audit --no-fund --cache .npm-cache
)

echo.
echo [INFO] 启动前端开发服务器 (http://localhost:5173)...
npm run dev

pause
