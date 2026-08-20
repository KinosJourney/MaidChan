# -*- coding: utf-8 -*-
"""路径与数据目录。

行为与原 ``oc.py`` 保持一致：

- 开发运行时，程序根目录 = 本仓库根（``pic/``、``readme.md``、``.env`` 所在处）。
  由于本文件位于 ``maidchan/config/paths.py``，需向上回溯两级才能得到仓库根。
- PyInstaller 打包后，沿用 ``sys.executable`` / ``sys._MEIPASS``。
- 用户数据（配置 / 档案 / 历史）仍写入系统用户目录，升级不丢失。
"""

import os
import sys

# 开发模式下的仓库根目录：paths.py -> config -> maidchan -> <root>
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def app_base_dir():
    """程序所在目录（兼容 PyInstaller 打包后的情况）。"""
    if getattr(sys, "frozen", False):
        # 打包后：可执行文件所在目录
        return os.path.dirname(sys.executable)
    return _PROJECT_ROOT


def resource_dir():
    """打包资源目录（图片等只读资源）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return _PROJECT_ROOT


def user_data_dir():
    """用户数据目录：保存聊天记录、配置、档案，升级不丢失。"""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "MaidChan")
    elif sys.platform.startswith("win"):
        base = os.path.join(os.environ.get("APPDATA", home), "MaidChan")
    else:
        base = os.path.join(home, ".maidchan")
    os.makedirs(base, exist_ok=True)
    return base


DATA_DIR = user_data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
MEMORY_PATH = os.path.join(DATA_DIR, "memories.json")
MEMORY_BACKUP_DIR = os.path.join(DATA_DIR, "backups")
POMODORO_STATS_PATH = os.path.join(DATA_DIR, "pomodoro_stats.json")
TODOS_PATH = os.path.join(DATA_DIR, "todos.json")
CONTENT_CACHE_PATH = os.path.join(DATA_DIR, "content_cache.json")

PIC_DIR = os.path.join(resource_dir(), "pic")
APP_ICON = os.path.join(PIC_DIR, "app-icon.png")
IMG_ORIGIN = os.path.join(PIC_DIR, "maid-chan-origin.png")
IMG_OPEN = os.path.join(PIC_DIR, "maid-chan-open-mouse.jpeg")
IMG_BLINK = os.path.join(PIC_DIR, "maii-chan-close-eye.png")
