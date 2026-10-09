@echo off
chcp 65001 >nul
rem MPV Config Builder -- launch from source (web UI).
rem Keep this file SHORT and ASCII-only above: cmd pre-reads the head of a .bat
rem with the console codepage (936 on a fresh window), so Chinese comment blocks
rem near the top get mis-decoded and executed as commands.
rem The five pitfalls behind this layout are documented in AGENTS.md 2.4
rem and docs\踩过的坑.md -- read those before editing.
cd /d "%~dp0"

echo 正在启动 MPV Config Builder ...
echo.

if not exist "webui\server.py" goto :nofile

rem Do NOT trust "where py": py.exe can exist while its runtime list is empty or
rem has no 3.x, and then "py -3" exits 103 while "where py" still returns 0 --
rem which would skip the python fallback entirely. So actually RUN it.
set "PYEXE="

:trypy
where py >nul 2>nul
if errorlevel 1 goto :trypython
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 goto :trypython
set "PYEXE=py -3"
goto :run

:trypython
where python >nul 2>nul
if errorlevel 1 goto :nopython
python -c "import sys" >nul 2>nul
if errorlevel 1 goto :nopython
set "PYEXE=python"
goto :run

:run
echo 使用解释器：%PYEXE%
%PYEXE% webui\server.py
if errorlevel 1 goto :failed
goto :eof

:nofile
echo [启动失败] 找不到 webui\server.py
echo 当前目录：%CD%
echo 请确认是在解压出来的项目根目录里运行本文件。
echo.
pause
goto :eof

:nopython
echo [启动失败] 没找到能用的 Python 3。
echo.
echo   已经试过 py -3 和 python，两个都跑不起来。
echo   想从源码跑：去 python.org 装一个，安装时记得勾选 "Add Python to PATH"。
echo   只是想把软件用起来：装 Electron 桌面版就行，不需要 Python。
echo.
pause
goto :eof

:failed
echo.
echo [启动失败] Python 报了错，往上翻看具体信息。
echo 常见原因：core\ 或 data\ 目录缺失（是不是只复制了部分文件？）
echo.
pause
goto :eof
