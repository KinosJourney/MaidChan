# -*- coding: utf-8 -*-
"""程序设置存储。"""

from ..config.constants import (
    DEFAULT_PLAYLIST_URL,
    DEFAULT_SYSTEM_PROMPT,
    PROACTIVE_CATEGORIES,
    PROACTIVE_CHAT_DAILY_LIMIT,
    PROACTIVE_CHAT_ENABLED_DEFAULT,
    PROACTIVE_CHAT_INTERVAL_MINUTES,
    PROACTIVE_CHAT_MIN_IDLE_MINUTES,
    PROACTIVE_CHAT_QUIET_END_HOUR,
    PROACTIVE_CHAT_QUIET_START_HOUR,
)
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
        self.data.setdefault("playlist_url", DEFAULT_PLAYLIST_URL)
        self.data.setdefault("stt_api_key", "")
        self.data.setdefault("stt_base_url", "")
        self.data.setdefault("stt_model", "")
        self.data.setdefault("stt_language", "")
        # 主动陪聊（空闲时主动聊新闻 / 八卦 / 哲学 / 稀奇知识）
        self.data.setdefault(
            "proactive_chat_enabled", PROACTIVE_CHAT_ENABLED_DEFAULT)
        self.data.setdefault(
            "proactive_chat_categories", list(PROACTIVE_CATEGORIES))
        self.data.setdefault(
            "proactive_chat_interval_minutes", PROACTIVE_CHAT_INTERVAL_MINUTES)
        self.data.setdefault(
            "proactive_chat_min_idle_minutes", PROACTIVE_CHAT_MIN_IDLE_MINUTES)
        self.data.setdefault(
            "proactive_chat_daily_limit", PROACTIVE_CHAT_DAILY_LIMIT)
        self.data.setdefault(
            "proactive_chat_quiet_start", PROACTIVE_CHAT_QUIET_START_HOUR)
        self.data.setdefault(
            "proactive_chat_quiet_end", PROACTIVE_CHAT_QUIET_END_HOUR)
        # 迁移：清除旧版本写入的 OpenAI 默认值，让 .env 生效
        if self.data.get("stt_base_url") == "https://api.openai.com/v1":
            self.data["stt_base_url"] = ""
        if self.data.get("stt_model") == "whisper-1":
            self.data["stt_model"] = ""

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        save_json(CONFIG_PATH, self.data)
