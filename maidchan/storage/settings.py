# -*- coding: utf-8 -*-
"""程序设置存储。"""

from ..config.constants import DEFAULT_SYSTEM_PROMPT
from ..config.paths import CONFIG_PATH
from .json_io import load_json, save_json


class Settings:
    def __init__(self):
        self.data = load_json(CONFIG_PATH, {})
        # 默认值
        self.data.setdefault("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.data.setdefault("always_on_top", True)
        self.data.setdefault("mute_anim", False)
        self.data.setdefault("show_input", True)
        self.data.setdefault("pos_x", None)
        self.data.setdefault("pos_y", None)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        save_json(CONFIG_PATH, self.data)
