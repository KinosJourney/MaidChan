#!/bin/bash
# ============================================================
# Maid-chan 桌宠 · 关闭开机自动启动（macOS）
# 双击运行即可取消开机自启。
# ============================================================

PLIST_NAME="com.maidchan.desktop-pet"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "============================================"
echo "  Maid-chan · 关闭开机启动"
echo "============================================"
echo ""

if [ ! -f "$PLIST_PATH" ]; then
    echo "当前没有开启开机启动，无需操作。"
    echo ""
    read -n 1 -s -r -p "按任意键退出…"
    exit 0
fi

launchctl unload "$PLIST_PATH" 2>/dev/null
rm -f "$PLIST_PATH"

echo "✔ 开机启动已关闭！"
echo "  下次登录 Mac 时，Maid-chan 不会自动启动了。"
echo "  你仍然可以随时双击 run.command 手动启动。"
echo ""
read -n 1 -s -r -p "按任意键退出…"
