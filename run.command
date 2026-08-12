#!/bin/bash
# ============================================================
# Maid-chan 桌宠 · macOS 一键启动脚本
# 双击运行即可让桌宠出现在桌面上。
# ============================================================

cd "$(dirname "$0")" || exit 1

# 如果还没安装过，提示先安装
if [ ! -d ".venv" ]; then
    echo "还没有安装运行环境，正在自动为你安装…"
    echo ""
    bash ./install.command
fi

# 激活虚拟环境
source .venv/bin/activate

echo "正在启动 Maid-chan 桌宠…（关闭本窗口不会关闭桌宠）"
# 使用 pythonw 风格：后台运行，不阻塞
python oc.py
