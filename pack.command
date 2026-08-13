#!/bin/bash
# ============================================================
# Maid-chan 桌宠 · macOS 一键打包脚本
# 双击运行后，会在 dist/ 文件夹里生成可双击的 Maid-chan.app
# 并自动制作包含 .env 模板和 readme 的 zip 分发包
# ============================================================

cd "$(dirname "$0")" || exit 1

echo "============================================"
echo "  Maid-chan 桌宠 · 打包程序 (macOS)"
echo "============================================"
echo ""

# 确保环境存在
if [ ! -d ".venv" ]; then
    echo "还没有安装运行环境，正在自动安装…"
    bash ./install.command
fi

source .venv/bin/activate

# 确保 pyinstaller 已安装
python -m pip install --upgrade pyinstaller >/dev/null 2>&1

echo "正在打包，请稍候（首次打包较慢）…"
echo ""

# --windowed 让 app 没有终端黑窗；--add-data 携带图片与 readme
# --collect-submodules maidchan 确保拆分后的所有子模块都被打包进去
python -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "Maid-chan" \
    --icon "pic/app-icon.png" \
    --collect-submodules maidchan \
    --add-data "pic:pic" \
    --add-data "readme.md:." \
    oc.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[错误] 打包失败，请把上面的信息截图求助。"
    echo ""
    read -n 1 -s -r -p "按任意键退出…"
    exit 1
fi

echo ""
echo "打包成功，正在制作分发包…"

# 制作分发目录
DIST_DIR="dist/Maid-chan-macOS"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 复制 app
cp -R dist/Maid-chan.app "$DIST_DIR/"

# 生成 .env 模板（不包含真实 Key）
cat > "$DIST_DIR/.env" << 'ENVEOF'
# 请把等号右侧替换为你的 DeepSeek API Key
# 获取地址：https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY=在此填入你的key
ENVEOF

# 复制使用说明
cp readme.md "$DIST_DIR/"

# 打包成 zip
cd dist
rm -f Maid-chan-macOS.zip
zip -r -y Maid-chan-macOS.zip Maid-chan-macOS/
cd ..

echo ""
echo "============================================"
echo "  全部完成！"
echo ""
echo "  分发包：dist/Maid-chan-macOS.zip"
echo ""
echo "  发给朋友后，解压 → 编辑 .env 填入 Key"
echo "  → 双击 Maid-chan.app 即可使用。"
echo ""
echo "  首次打开若提示无法验证开发者："
echo "  右键 Maid-chan.app → 打开 → 打开"
echo "============================================"

echo ""
read -n 1 -s -r -p "按任意键退出…"
