@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 MPV Config Builder（新版界面）...
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 webui\server.py
) else (
    python webui\server.py
)
if errorlevel 1 (
    echo.
    echo [启动失败] 请确认已安装 Python 3，并且 core\ 与 webui\ 目录都在本目录下。
    pause
)
