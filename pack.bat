@echo off
chcp 65001 >nul
REM ============================================================
REM  Maid-chan 桌宠 · Windows 一键打包脚本
REM  双击运行后，会在 dist\ 文件夹里生成 Maid-chan.exe
REM ============================================================

cd /d "%~dp0"

echo ============================================
echo   Maid-chan 桌宠 · 打包程序 (Windows)
echo ============================================
echo.

if not exist ".venv" (
    echo 还没有安装运行环境，正在自动安装...
    call install.bat
)

call .venv\Scripts\activate.bat

python -m pip install --upgrade pyinstaller >nul 2>nul

echo 正在打包，请稍候（首次打包较慢）...
echo.

REM --windowed 不弹黑窗；--add-data 用分号分隔（Windows）
python -m PyInstaller ^
    --noconfirm ^
    --windowed ^
    --name "Maid-chan" ^
    --add-data "pic;pic" ^
    --add-data "readme.md;." ^
    oc.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请把上面的信息截图求助。
) else (
    echo.
    echo ============================================
    echo   打包完成！
    echo   生成的程序在：dist\Maid-chan\Maid-chan.exe
    echo   提示：readme.md 也可放在 exe 旁边，随时手动修改。
    echo ============================================
)

echo.
pause
