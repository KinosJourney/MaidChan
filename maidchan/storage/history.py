# -*- coding: utf-8 -*-
"""聊天历史存储。"""

import random
import time
from datetime import datetime

from .json_io import load_json, save_json


class HistoryStore:
    """管理聊天历史：读写本地 JSON，支持单条删除。"""

    def __init__(self, path):
        self.path = path
        self.items = load_json(path, [])
        if not isinstance(self.items, list):
            self.items = []

    def add(self, role, content):
        item = {
            "id": "%d_%04d" % (int(time.time() * 1000), random.randint(0, 9999)),
            "role": role,  # "user" 或 "maid"
            "content": content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.items.append(item)
        self.save()
        return item

    def delete(self, item_id):
        before = len(self.items)
        self.items = [it for it in self.items if it.get("id") != item_id]
        if len(self.items) != before:
            self.save()
            return True
        return False

    def clear(self):
        self.items = []
        self.save()

    def save(self):
        save_json(self.path, self.items)

    def context_messages(self, max_turns):
        """把最近的历史转成 API 需要的 messages（不含 system）。"""
        msgs = []
        for it in self.items:
            role = "user" if it.get("role") == "user" else "assistant"
            msgs.append({"role": role, "content": it.get("content", "")})
        # 只保留最近 max_turns*2 条
        limit = max_turns * 2
        if len(msgs) > limit:
            msgs = msgs[-limit:]
        return msgs
