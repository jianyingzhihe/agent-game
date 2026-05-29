@echo off
cd /d "E:\agent game\ai-game-platform"
echo === 三国杀 Round-Table Viewer ===
echo 使用 conda Python (pygame 支持)
echo.
"e:\code\conda\python.exe" -m sgs_viewer %*
if %errorlevel% neq 0 (
    echo.
    echo 启动失败！请确认：
    echo 1. conda Python 在 e:\code\conda\python.exe
    echo 2. 已安装 pygame (pip install pygame)
    echo 3. 日志文件在 logs/sanguosha/ 目录下
    pause
)
