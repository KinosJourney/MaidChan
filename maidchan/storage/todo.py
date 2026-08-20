# -*- coding: utf-8 -*-
"""待办事项存储。

与聊天历史 / 长期记忆分离：这里只记录「有截止时间、需要到点提醒的临时事项」。
每条待办在截止前 ``REMINDER_ADVANCE_MINUTES`` 分钟提醒一次、到点再提醒一次，
提醒是否已发出用 ``pre_reminded_at`` / ``due_reminded_at`` 两个标记去重，
即使应用重启也不会重复轰炸。
"""

import random
import time
from datetime import datetime, timedelta

from .json_io import load_json, save_json
from ..config.constants import DATETIME_FMT, REMINDER_ADVANCE_MINUTES

STATUS_PENDING = "pending"
STATUS_DONE = "done"


def parse_dt(value):
    """把时间字符串解析成 ``datetime``；无法解析返回 ``None``。"""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(value, DATETIME_FMT)
    except (ValueError, TypeError):
        return None


def format_dt(value):
    """把 ``datetime`` 格式化成统一字符串；已是字符串则原样返回。"""
    if isinstance(value, datetime):
        return value.strftime(DATETIME_FMT)
    return value or ""


class TodoStore:
    """管理待办事项：增删改查、状态切换、提醒标记、待提醒查询。"""

    def __init__(self, path, advance_minutes=REMINDER_ADVANCE_MINUTES):
        self.path = path
        self.advance_minutes = advance_minutes
        self.items = load_json(path, [])
        if not isinstance(self.items, list):
            self.items = []

    # ---- 增 ----
    def add(self, content, due_at, source="manual", now=None):
        """添加一条待办。

        ``due_at`` 可以是 ``datetime`` 或统一格式字符串。若创建时距离截止已不足
        ``advance_minutes`` 分钟，则预先把提前提醒标记为已发出（跳过提前提醒，
        只保留到点提醒），与需求一致。
        """
        content = (content or "").strip()
        due_dt = parse_dt(due_at)
        if not content or due_dt is None:
            return None

        now = now or datetime.now()
        now_str = now.strftime(DATETIME_FMT)
        pre_time = due_dt - timedelta(minutes=self.advance_minutes)
        # 创建时已错过提前提醒窗口 -> 直接标记，跳过提前提醒。
        pre_reminded_at = now_str if now >= pre_time else None

        item = {
            "id": "todo_%d_%04d" % (int(time.time() * 1000), random.randint(0, 9999)),
            "content": content,
            "due_at": format_dt(due_dt),
            "status": STATUS_PENDING,
            "created_at": now_str,
            "updated_at": now_str,
            "pre_reminded_at": pre_reminded_at,
            "due_reminded_at": None,
            "source": source,
        }
        self.items.append(item)
        self.save()
        return item

    # ---- 删 ----
    def delete(self, todo_id):
        before = len(self.items)
        self.items = [t for t in self.items if t.get("id") != todo_id]
        if len(self.items) != before:
            self.save()
            return True
        return False

    def clear(self):
        self.items = []
        self.save()

    # ---- 改 ----
    def update(self, todo_id, content=None, due_at=None, now=None):
        """修改内容 / 截止时间。改动截止时间会重置提醒标记，让新时间重新提醒。"""
        item = self.get(todo_id)
        if item is None:
            return False
        now = now or datetime.now()
        now_str = now.strftime(DATETIME_FMT)
        changed = False

        if content is not None:
            content = content.strip()
            if content and content != item.get("content"):
                item["content"] = content
                changed = True

        if due_at is not None:
            due_dt = parse_dt(due_at)
            if due_dt is not None and format_dt(due_dt) != item.get("due_at"):
                item["due_at"] = format_dt(due_dt)
                pre_time = due_dt - timedelta(minutes=self.advance_minutes)
                item["pre_reminded_at"] = now_str if now >= pre_time else None
                item["due_reminded_at"] = None
                changed = True

        if changed:
            item["updated_at"] = now_str
            self.save()
        return changed

    def set_status(self, todo_id, status, now=None):
        item = self.get(todo_id)
        if item is None or status not in (STATUS_PENDING, STATUS_DONE):
            return False
        item["status"] = status
        item["updated_at"] = (now or datetime.now()).strftime(DATETIME_FMT)
        self.save()
        return True

    def mark_done(self, todo_id, now=None):
        return self.set_status(todo_id, STATUS_DONE, now=now)

    def mark_pending(self, todo_id, now=None):
        return self.set_status(todo_id, STATUS_PENDING, now=now)

    def mark_pre_reminded(self, todo_id, now=None):
        item = self.get(todo_id)
        if item is None:
            return False
        item["pre_reminded_at"] = (now or datetime.now()).strftime(DATETIME_FMT)
        self.save()
        return True

    def mark_due_reminded(self, todo_id, now=None):
        """标记到点提醒已发出，同时把提前提醒也置为已发（避免补发提前提醒）。"""
        item = self.get(todo_id)
        if item is None:
            return False
        now_str = (now or datetime.now()).strftime(DATETIME_FMT)
        item["due_reminded_at"] = now_str
        if not item.get("pre_reminded_at"):
            item["pre_reminded_at"] = now_str
        self.save()
        return True

    # ---- 查 ----
    def get(self, todo_id):
        for t in self.items:
            if t.get("id") == todo_id:
                return t
        return None

    def pending(self):
        return [t for t in self.items if t.get("status") == STATUS_PENDING]

    def done(self):
        return [t for t in self.items if t.get("status") == STATUS_DONE]

    def sorted_pending(self):
        """未完成待办按截止时间升序（无法解析时间的排在最后）。"""
        far = datetime.max

        def key(t):
            return parse_dt(t.get("due_at")) or far

        return sorted(self.pending(), key=key)

    @property
    def pending_count(self):
        return len(self.pending())

    def save(self):
        save_json(self.path, self.items)
