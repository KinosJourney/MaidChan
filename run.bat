@echo off
chcp 65001 >nul
REM ============================================================
REM  Maid-chan 桌宠 · Windows 一键启动脚本
REM  双击运行即可让桌宠出现在桌面上。
REM ============================================================

cd /d "%~dp0"

REM 若未安装则先自动安装
if not exist ".venv" (
    echo 还没有安装运行环境，正在自动为你安装...
    echo.
    call install.bat
)

call .venv\Scripts\activate.bat

echo 正在启动 Maid-chan 桌宠...
REM 用 pythonw 启动，不显示黑色命令行窗口
start "" .venv\Scripts\pythonw.exe oc.py
