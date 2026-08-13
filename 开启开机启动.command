#!/bin/bash
# ============================================================
# Maid-chan 桌宠 · 开启开机自动启动（macOS）
# 双击运行即可。登录 Mac 后桌宠会自动出现。
# ============================================================

cd "$(dirname "$0")" || exit 1
PROJECT_DIR="$(pwd)"

PLIST_NAME="com.maidchan.desktop-pet"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME.plist"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/oc.py"

echo "============================================"
echo "  Maid-chan · 开启开机启动"
echo "============================================"
echo ""

# 检查虚拟环境
if [ ! -f "$PYTHON_BIN" ]; then
    echo "[错误] 没有找到运行环境 (.venv)。"
    echo "请先双击 install.command 完成安装，再来开启开机启动。"
    echo ""
    read -n 1 -s -r -p "按任意键退出…"
    exit 1
fi

mkdir -p "$PLIST_DIR"

# 写入 LaunchAgent plist
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${SCRIPT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONIOENCODING</key>
        <string>utf-8</string>
    </dict>

    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/maidchan-launch.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/maidchan-launch.log</string>
</dict>
</plist>
PLIST

echo "✔ 开机启动已开启！"
echo ""
echo "  plist 路径：$PLIST_PATH"
echo "  下次登录 Mac 时，Maid-chan 会自动出现在桌面上。"
echo ""
read -n 1 -s -r -p "按任意键退出…"
