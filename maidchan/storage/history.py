# -*- coding: utf-8 -*-
"""聊天历史存储。

历史记录保存所有对话原文（共同经历），同时提供会话感知：
超过一定时间未互动后，context_messages 只返回新会话的消息。
"""

import random
import time
from datetime import datetime

from .json_io import load_json, save_json

from ..config.constants import SESSION_TIMEOUT_SECONDS


class HistoryStore:
    """管理聊天历史：读写本地 JSON，支持单条删除，会话感知上下文。"""

    def __init__(self, path):
        self.path = path
        self.items = load_json(path, [])
        if not isinstance(self.items, list):
            self.items = []
        self._session_start_idx = self._detect_session_start()

    def _detect_session_start(self):
        """检测当前会话的起始位置：从最后一条往前找超时断点。"""
        if not self.items:
            return 0
        now = datetime.now()
        for i in range(len(self.items) - 1, -1, -1):
            item_time = self._parse_time(self.items[i])
            if item_time is None:
                continue
            gap = (now - item_time).total_seconds()
            if gap > SESSION_TIMEOUT_SECONDS:
                return i + 1
        return 0

    def _parse_time(self, item):
        try:
            return datetime.strptime(item.get("time", ""), "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    def new_session(self):
        """手动开启新会话（不删除历史）。"""
        self._session_start_idx = len(self.items)

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
            self._session_start_idx = min(self._session_start_idx, len(self.items))
            self.save()
            return True
        return False

    def clear(self):
        self.items = []
        self._session_start_idx = 0
        self.save()

    def save(self):
        save_json(self.path, self.items)

    def context_messages(self, max_turns):
        """把当前会话的历史转成 API 需要的 messages（不含 system）。

        只返回当前会话内的消息，且限制最大轮数。
        """
        self._check_session_timeout()
        session_items = self.items[self._session_start_idx:]
        msgs = []
        for it in session_items:
            role = "user" if it.get("role") == "user" else "assistant"
            msgs.append({"role": role, "content": it.get("content", "")})
        limit = max_turns * 2
        if len(msgs) > limit:
            msgs = msgs[-limit:]
        return msgs

    def _check_session_timeout(self):
        """检查最后一条消息是否超时，超时则开启新会话。"""
        if not self.items:
            return
        last = self.items[-1]
        last_time = self._parse_time(last)
        if last_time is None:
            return
        gap = (datetime.now() - last_time).total_seconds()
        if gap > SESSION_TIMEOUT_SECONDS:
            self._session_start_idx = len(self.items)

    @property
    def last_message_id(self):
        """返回最后一条消息的 id。"""
        if self.items:
            return self.items[-1].get("id")
        return None
