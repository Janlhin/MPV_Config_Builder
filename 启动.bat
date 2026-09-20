﻿@echo off
rem ===========================================================================
rem  MPV Config Builder —— 从源码启动（网页版）
rem
rem  给"本机有 Python、想直接跑源码"的人用。
rem  **普通用户不需要这个** —— 装 Electron 桌面版即可（不需要 Python）。
rem
rem  ⚠ 这个文件踩过三个坑，改的时候别踩回去：
rem    1. **文件名不能带半角括号**。原来叫「启动(新版界面).bat」，
rem       cmd 解析到括号就断，直接报 `'启动' 不是内部或外部命令`。
rem    2. **必须是 CRLF 行尾**。LF 的批处理在 Windows 上行为不可靠。
rem    3. **必须带 UTF-8 BOM**。文件里有中文 echo，而 chcp 65001 要等这一行
rem       执行完才生效 —— 没有 BOM 的话，chcp 之前那行中文就已经乱码了。
rem       带 BOM 的 UTF-8 是现代 cmd 认得的编码，中文能正常显示。
rem    4. 下面用 goto 而不是 if(...) 括号块：括号块里的 %errorlevel% 是
rem       **解析时**展开的，不是执行时，判断会失效。
rem ===========================================================================
chcp 65001 >nul
cd /d "%~dp0"

echo 正在启动 MPV Config Builder ...
echo.

if not exist "webui\server.py" goto :nofile

set "PYEXE="
where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE goto :nopython

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
echo [启动失败] 没找到 Python 3。
echo.
echo   想从源码跑：去 python.org 装一个，安装时记得勾选 "Add Python to PATH"。
echo   只是想把软件用起来：装 Electron 桌面版就行，**不需要 Python**。
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
