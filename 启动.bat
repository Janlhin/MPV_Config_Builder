@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 mpv_config_builder.py
) else (
    python mpv_config_builder.py
)
if errorlevel 1 (
    echo.
    echo [启动失败] 请先安装 Python 3（安装时勾选 Add Python to PATH），或使用打包后的 exe。
    pause
)
