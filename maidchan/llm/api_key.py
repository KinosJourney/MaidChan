# -*- coding: utf-8 -*-
"""DeepSeek API Key 读取。

优先环境变量，其次读取「程序目录」下的 ``.env``。这里使用
``app_base_dir()`` 而非 ``__file__``，因此：

- 开发运行时读取仓库根的 ``.env``；
- 打包后读取可执行文件（``.app`` / ``.exe``）旁的 ``.env``。
"""

import os

from ..config.paths import app_base_dir


def get_deepseek_api_key():
    """优先读取环境变量，其次读取程序目录下的 .env 文件。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if api_key:
        return api_key

    env_path = os.path.join(app_base_dir(), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                name, separator, value = line.strip().partition("=")
                if separator and name.strip() == "DEEPSEEK_API_KEY":
                    return value.strip().strip("\"'")
    except OSError:
        pass
    return ""
