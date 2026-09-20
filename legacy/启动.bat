@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem 旧界面（Tkinter）启动器
rem
rem ⚠ 必须先退到**仓库根**再启动：
rem   旧程序要 import core\、要读 data\ 与根目录的 *.md，那些都不在 legacy\ 下。
rem   （程序自己也补了 sys.path，但工作目录该对还是得对，否则它按相对路径
rem     找配置与文档时又是另一套行为。）
rem
rem 这个界面已定「保留但不维护」。新界面请用根目录的 启动(新版界面).bat；
rem 装好的用户直接开「MPV Config Builder」。
rem ---------------------------------------------------------------------------
cd /d "%~dp0.."

if not exist "legacy\mpv_config_builder.py" (
    echo.
    echo [启动失败] 找不到 legacy\mpv_config_builder.py
    echo 当前目录：%CD%
    pause
    exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 legacy\mpv_config_builder.py
) else (
    python legacy\mpv_config_builder.py
)

if errorlevel 1 (
    echo.
    echo [启动失败] 请先安装 Python 3（安装时勾选 Add Python to PATH），或使用打包后的 exe。
    pause
)
