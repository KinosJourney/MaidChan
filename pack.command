#!/bin/bash
# ============================================================
# Maid-chan 桌宠 · macOS 一键打包脚本
# 双击运行后，会在 dist/ 文件夹里生成可双击的 Maid-chan.app
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

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================"
    echo "  打包完成！"
    echo "  生成的应用在：dist/Maid-chan.app"
    echo "  可以把它拖到『应用程序』里，双击运行。"
    echo "  提示：readme.md 也可放在 app 旁边，随时手动修改。"
    echo "============================================"
else
    echo ""
    echo "[错误] 打包失败，请把上面的信息截图求助。"
fi

echo ""
read -n 1 -s -r -p "按任意键退出…"
