# -*- coding: utf-8 -*-
"""DeepSeek API Key 读取。

优先环境变量，其次读取 ``.env``：

- 开发运行时读取仓库根的 ``.env``；
- 打包后优先读取系统用户数据目录中的 ``.env``，不会把 Key 放进应用包。
"""

import os

from ..config.paths import env_file_candidates


def get_deepseek_api_key():
    """优先读取环境变量，其次按平台约定读取 .env 文件。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if api_key:
        return api_key

    for env_path in env_file_candidates():
        try:
            with open(env_path, "r", encoding="utf-8") as env_file:
                for line in env_file:
                    name, separator, value = line.strip().partition("=")
                    if separator and name.strip() == "DEEPSEEK_API_KEY":
                        return value.strip().strip("\"'")
        except OSError:
            continue
    return ""
