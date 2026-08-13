# -*- coding: utf-8 -*-
"""B 站合集随机播放。"""

from .bilibili import (
    CollectionError,
    PlaylistWorker,
    fetch_collection_videos,
    parse_collection_url,
    pick_random,
    short_title,
)
from .hotkey import GlobalHotkey, hotkey_display, qt_key_sequence

__all__ = [
    "CollectionError",
    "PlaylistWorker",
    "fetch_collection_videos",
    "parse_collection_url",
    "pick_random",
    "short_title",
    "GlobalHotkey",
    "hotkey_display",
    "qt_key_sequence",
]
