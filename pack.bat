@echo off
chcp 65001 >nul
REM ============================================================
REM  Maid-chan 桌宠 · Windows 一键打包脚本
REM  双击运行后，会在 dist\ 文件夹里生成 Maid-chan.exe
REM  并自动制作包含 .env 模板和 readme 的 zip 分发包
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
REM --collect-submodules maidchan 确保拆分后的所有子模块都被打包进去
python -m PyInstaller ^
    --noconfirm ^
    --windowed ^
    --name "Maid-chan" ^
    --icon "pic\app-icon.png" ^
    --collect-submodules maidchan ^
    --add-data "pic;pic" ^
    --add-data "readme.md;." ^
    oc.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请把上面的信息截图求助。
    echo.
    pause
    exit /b 1
)

echo.
echo 打包成功，正在制作分发包...

REM 制作分发目录
set DIST_DIR=dist\Maid-chan-Windows
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%"

REM 复制程序目录
xcopy /e /i /q "dist\Maid-chan" "%DIST_DIR%\Maid-chan"

REM 生成 .env 模板（不包含真实 Key）
(
echo # 请把等号右侧替换为你的 DeepSeek API Key
echo # 获取地址：https://platform.deepseek.com/api_keys
echo DEEPSEEK_API_KEY=在此填入你的key
) > "%DIST_DIR%\.env"

REM 复制使用说明
copy /y readme.md "%DIST_DIR%\" >nul

REM 打包成 zip（使用 PowerShell）
del /q "dist\Maid-chan-Windows.zip" 2>nul
powershell -Command "Compress-Archive -Path 'dist\Maid-chan-Windows\*' -DestinationPath 'dist\Maid-chan-Windows.zip' -Force"

echo.
echo ============================================
echo   全部完成！
echo.
echo   分发包：dist\Maid-chan-Windows.zip
echo.
echo   发给朋友后，解压 → 编辑 .env 填入 Key
echo   → 双击 Maid-chan\Maid-chan.exe 即可使用。
echo ============================================

echo.
pause
