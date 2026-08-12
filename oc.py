# -*- coding: utf-8 -*-
"""
Maid-chan 桌宠 (Sakurasou "Maid" AI) · 启动入口
================================================

一个透明、可拖拽、常驻桌面的桌面宠物，使用 DeepSeek API 实现智能对话。

角色设定来自《樱花庄的宠物女孩》中赤坂龙之介编写的 AI「Maid（メイド）」：
高智能、敏捷、自信、精通计算机，会主动学习、略带傲娇。

本文件现在只是一个「启动入口」：真正的实现已拆分到 maidchan/ 包中，
方便后续扩展（状态机、调度器、通知等）。直接 `python oc.py` 即可运行，
行为与打包方式保持不变。

DeepSeek API Key 通过环境变量或程序目录下的 .env 文件提供，不写入源码。
"""

import sys


def main():
    try:
        from maidchan.app import main as app_main
    except ImportError as exc:
        # 最常见的原因是缺少 PySide6 等依赖。
        print("=" * 60)
        print("启动失败：%s" % exc)
        print("可能是缺少依赖库（如 PySide6）。")
        print("请先双击运行 install.command (macOS) 或 install.bat (Windows)。")
        print("或手动执行：pip install PySide6 requests Pillow")
        print("=" * 60)
        sys.exit(1)
    app_main()


if __name__ == "__main__":
    main()
