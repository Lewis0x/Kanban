@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3 并加入 PATH。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境 .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [错误] 创建虚拟环境失败。
    pause
    exit /b 1
  )
)

echo 正在安装/更新依赖...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [错误] pip install 失败。
  pause
  exit /b 1
)

echo.
echo ========================================
echo   看板已启动
echo   浏览器打开: http://127.0.0.1:5000
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

".venv\Scripts\python.exe" -m flask --app app.main run --debug

echo.
pause
