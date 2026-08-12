@echo off
chcp 65001 >nul
REM ============================================================
REM  Maid-chan 桌宠 · Windows 一键安装脚本
REM  双击运行即可。自动创建独立环境并安装所需的库。
REM ============================================================

cd /d "%~dp0"

echo ============================================
echo   Maid-chan 桌宠 · 安装程序 (Windows)
echo ============================================
echo.

REM 检测 python
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有检测到 Python。
    echo 请先到 https://www.python.org/downloads/ 下载安装 Python 3，
    echo 安装时记得勾选 "Add Python to PATH"，然后重新运行本程序。
    echo.
    pause
    exit /b 1
)

echo 使用的 Python：
python --version
echo.

REM 创建虚拟环境
if not exist ".venv" (
    echo 正在创建独立运行环境 (.venv) ...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo 正在升级 pip ...
python -m pip install --upgrade pip

echo.
echo 正在安装依赖库（PySide6 / requests / Pillow / pyinstaller）...
echo 第一次安装可能需要几分钟，请耐心等待。
echo.
set PYTHONIOENCODING=utf-8
REM --no-compile 跳过 pip 预编译字节码，避开 PySide6 里非法模板文件导致的崩溃
python -m pip install --no-compile -r requirements.txt

if errorlevel 1 (
    echo.
    echo [错误] 安装过程中出现问题，请把上面的信息截图求助。
) else (
    echo.
    echo ============================================
    echo   安装完成！
    echo   接下来双击 run.bat 即可启动桌宠。
    echo   请按 readme.md 在 .env 文件中填写 DeepSeek API Key。
    echo ============================================
)

echo.
pause
