@echo off
setlocal
title CheepSeek Radar - Diagnostic Mode
cd /d "%~dp0"

rem ============================================================
rem  这是【诊断模式】启动脚本（保留控制台窗口，能看到日志）
rem  日常使用请双击同目录的「打开监控台.vbs」——静默启动、无窗口
rem  仅当 vbs 启动异常时，用本脚本排查问题
rem ============================================================
echo.
echo  提示：日常使用请双击「打开监控台.vbs」（无窗口、更省事）。
echo        本窗口是诊断模式，会显示运行日志，关掉窗口即停止服务。
echo.

rem ---- find a real Python (skip WindowsApps stub) ----
set "PYCMD="
set "FOUND_PY="

for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /i "WindowsApps" >nul 2>nul
    if errorlevel 1 set "PYCMD=python" & goto found
)
for /d %%D in ("%USERPROFILE%\AppData\Roaming\uv\python\cpython-*") do (
    if exist "%%D\python.exe" set "FOUND_PY=%%D\python.exe" & goto found
)
if exist "%USERPROFILE%\.agent-reach\.venv\Scripts\python.exe" (
    set "PYCMD=call "%USERPROFILE%\.agent-reach\.venv\Scripts\python.exe""
    goto found
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "FOUND_PY=%%D\python.exe" & goto found
)
goto no_python

:found
if defined FOUND_PY set "PYCMD=call "%FOUND_PY%""
if not defined PYCMD goto no_python
echo Using Python: %PYCMD%

netstat -ano | findstr ":8765" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo Dashboard already running. Opening browser...
    start "" "http://127.0.0.1:8765/"
    exit /b 0
)

echo [1/2] Starting dashboard service on port 8765...
%PYCMD% -u server.py --port 8765 --open 2> server_error.log
if errorlevel 1 (
    echo.
    echo [ERROR] Service failed to start. Details below:
    echo ----------------------------------------
    if exist server_error.log type server_error.log
    echo ----------------------------------------
    echo Please send the message above to the developer.
    pause
    exit /b 1
)

echo.
echo [2/2] Service stopped. You can close this window.
pause
exit /b 0

:no_python
echo [ERROR] Python 3 not found on this machine.
echo Please install Python from https://www.python.org/downloads/
echo then double-click this script again.
pause
exit /b 1
