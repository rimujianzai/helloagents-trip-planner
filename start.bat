@echo off
chcp 65001 >nul
cd /d %~dp0

echo ============================================
echo   HelloAgents 智能旅行助手 - 启动中
echo ============================================
echo.

echo [1/3] 启动后端 (端口 8000)...
start "trip-planner-backend" cmd /k "cd /d %~dp0backend && venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --port 8000"

echo [2/3] 启动前端 (端口 5173)...
start "trip-planner-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo [3/3] 等待服务就绪...
timeout /t 8 /nobreak >nul

echo.
echo 完成! 浏览器即将打开 http://localhost:5173
echo 注意: 那两个新开的窗口不要关闭, 关掉服务就停了.
echo.
start http://localhost:5173
