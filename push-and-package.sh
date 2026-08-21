#!/bin/bash
# Push 当前分支；成功后打包、替换并启动本机 Maid-chan.app。

set -u

cd "$(dirname "$0")" || exit 1

APP_NAME="Maid-chan.app"
BUILD_APP="$PWD/dist/$APP_NAME"
INSTALL_DIR="$HOME/Applications"
INSTALLED_APP="$INSTALL_DIR/$APP_NAME"
NEW_APP="$INSTALL_DIR/.Maid-chan.app.new"
BACKUP_APP="$INSTALL_DIR/.Maid-chan.app.backup"

echo "============================================"
echo "  Maid-chan · Push 后自动打包"
echo "============================================"
echo ""

# 确保打包内容与刚刚 push 的提交完全一致。
if [ -n "$(git status --porcelain)" ]; then
    echo "[停止] 工作区还有未提交的修改。"
    echo "请先提交全部修改，再重新运行本脚本。"
    exit 1
fi

echo "正在 push 当前分支…"
if ! git push "$@"; then
    echo ""
    echo "[停止] git push 失败，未执行打包和替换。"
    exit 1
fi

echo ""
echo "Push 成功，开始打包…"

if [ ! -x ".venv/bin/python" ]; then
    echo "未找到运行环境，正在安装…"
    if ! bash ./install.command; then
        echo "[停止] 运行环境安装失败。"
        exit 1
    fi
fi

if ! .venv/bin/python -c "import PyInstaller" >/dev/null 2>&1; then
    echo "正在安装 PyInstaller…"
    if ! .venv/bin/python -m pip install "pyinstaller>=6,<7"; then
        echo "[停止] PyInstaller 安装失败。"
        exit 1
    fi
fi

export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache"

if ! .venv/bin/python -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "Maid-chan" \
    --osx-bundle-identifier "com.maidchan.desktop" \
    --icon "pic/app-icon.png" \
    --collect-submodules maidchan \
    --add-data "pic:pic" \
    --add-data "readme.md:." \
    oc.py; then
    echo ""
    echo "[停止] 打包失败；已安装的旧版本保持不变。"
    exit 1
fi

if [ ! -d "$BUILD_APP" ]; then
    echo "[停止] 未找到打包产物：$BUILD_APP"
    exit 1
fi

echo ""
echo "打包成功，正在安全替换本机应用…"

mkdir -p "$INSTALL_DIR"
rm -rf "$NEW_APP" "$BACKUP_APP"

if ! ditto "$BUILD_APP" "$NEW_APP"; then
    echo "[停止] 复制新应用失败；已安装的旧版本保持不变。"
    rm -rf "$NEW_APP"
    exit 1
fi

if ! codesign --verify --deep --strict "$NEW_APP"; then
    echo "[停止] 新应用签名验证失败；已安装的旧版本保持不变。"
    rm -rf "$NEW_APP"
    exit 1
fi

# 只关闭安装目录中的打包版，不影响通过 python oc.py 运行的开发版。
pkill -f "$INSTALLED_APP/Contents/MacOS/Maid-chan" 2>/dev/null || true

if [ -e "$INSTALLED_APP" ]; then
    mv "$INSTALLED_APP" "$BACKUP_APP"
fi

if ! mv "$NEW_APP" "$INSTALLED_APP"; then
    echo "[错误] 替换应用失败，正在恢复旧版本…"
    if [ -e "$BACKUP_APP" ]; then
        mv "$BACKUP_APP" "$INSTALLED_APP"
    fi
    exit 1
fi

rm -rf "$BACKUP_APP"
mdimport "$INSTALLED_APP"
open "$INSTALLED_APP"

echo ""
echo "============================================"
echo "  完成：Push、打包、替换和启动均成功"
echo "  $INSTALLED_APP"
echo "============================================"
