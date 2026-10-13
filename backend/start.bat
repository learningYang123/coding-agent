@echo off
chcp 65001 >nul
echo ============================================
echo   企业代码智能助手 - 后端服务启动
echo ============================================
echo.

rem 切换到项目根目录（数据和 .env 均在根目录，保证 ./data 路径一致）
cd /d "%~dp0.."

rem 使用 uv 创建的项目虚拟环境
set "PY_CMD=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY_CMD%" (
    echo [ERROR] 未找到虚拟环境: %PY_CMD%
    echo         请先执行:
    echo         cd /d "%~dp0.."
    echo         uv venv --python 3.12
    echo         uv pip install torch --index-url https://download.pytorch.org/whl/cpu
    echo         uv pip install -r backend\requirements.txt
    pause
    exit /b 1
)

if not exist ".env" (
    echo [INFO] 未找到 .env，从 backend\.env.example 复制...
    copy "backend\.env.example" ".env"
)

echo [INFO] 检查依赖...
"%PY_CMD%" -c "import fastapi, uvicorn, cryptography" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 正在安装依赖...
    uv pip install -r backend\requirements.txt
)

echo.
echo [INFO] 启动后端服务 (http://localhost:8000)...
"%PY_CMD%" backend\run.py

pause
