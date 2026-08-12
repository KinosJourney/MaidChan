#!/bin/bash
# ============================================================
# Maid-chan 桌宠 · macOS 一键安装脚本
# 双击运行即可。它会自动创建独立环境并安装所需的库。
# ============================================================

# 切换到脚本所在目录
cd "$(dirname "$0")" || exit 1

echo "============================================"
echo "  Maid-chan 桌宠 · 安装程序 (macOS)"
echo "============================================"
echo ""

# 找到 python3（优先选用更新的版本，避免 Xcode 自带的 3.9 出问题）
PY=""
for cand in python3.12 python3.11 python3.10 python3.13 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "[错误] 没有检测到 Python3。"
    echo "请先到 https://www.python.org/downloads/ 下载安装 Python 3，再重新运行本程序。"
    echo ""
    read -n 1 -s -r -p "按任意键退出…"
    exit 1
fi

# 避免管道输出时 stdout 编码为 None 导致的报错
export PYTHONIOENCODING=utf-8

echo "使用的 Python：$($PY --version)"
echo ""

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "正在创建独立运行环境 (.venv) …"
    $PY -m venv .venv
fi

# 激活虚拟环境
source .venv/bin/activate

echo "正在升级 pip …"
python -m pip install --upgrade pip

echo ""
echo "正在安装依赖库（PySide6 / requests / Pillow / pyinstaller）…"
echo "第一次安装可能需要几分钟，请耐心等待。"
echo ""
# --no-compile 跳过 pip 预编译字节码，避开 PySide6 里非法模板文件导致的崩溃
python -m pip install --no-compile -r requirements.txt

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================"
    echo "  安装完成！"
    echo "  接下来双击 run.command 即可启动桌宠。"
    echo "  请按 readme.md 在 .env 文件中填写 DeepSeek API Key。"
    echo "============================================"
else
    echo ""
    echo "[错误] 安装过程中出现问题，请把上面的红色信息截图求助。"
fi

echo ""
read -n 1 -s -r -p "按任意键退出…"
