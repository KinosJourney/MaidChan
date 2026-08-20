# -*- coding: utf-8 -*-
"""主动陪聊内容缓存。

保存各类别最近抓取到的条目、以及“已经聊过”的条目 id（跨重启去重）。
新闻 / 八卦来自 RSS，会被最新抓取结果替换；哲学 / 冷知识来自本地话题池，
始终可用。挑选时优先给没聊过的，全部聊过后再循环，避免无限重复。
"""

import random
import time

from .json_io import load_json, save_json
from ..config.constants import (
    CONTENT_FEED_MAX_ITEMS_PER_CATEGORY,
    CONTENT_USED_UID_LIMIT,
)


def _uid(item):
    return item.get("uid") or item.get("link") or item.get("title") or ""


class ContentCache:
    """内容条目缓存与“已聊过”去重。

    Parameters
    ----------
    path : str
        JSON 持久化路径。
    local_pools : dict | None
        本地话题池 ``{category: [item, ...]}``（哲学 / 冷知识），始终可用。
    max_items : int
        每个类别缓存的最大条目数。
    used_limit : int
        “已聊过” id 的最大记忆条数，超出后丢弃最旧的。
    """

    def __init__(self, path, local_pools=None,
                 max_items=CONTENT_FEED_MAX_ITEMS_PER_CATEGORY,
                 used_limit=CONTENT_USED_UID_LIMIT):
        self.path = path
        self._max_items = max_items
        self._used_limit = used_limit
        self._local_pools = local_pools or {}

        data = load_json(path, {})
        if not isinstance(data, dict):
            data = {}
        self.items = data.get("items", {})
        if not isinstance(self.items, dict):
            self.items = {}
        used = data.get("used_uids", [])
        self._used_order = [u for u in used if isinstance(u, str)]
        self._used = set(self._used_order)
        self.refreshed_at = data.get("refreshed_at")

        # 本地池：若缓存里还没有该类别内容，用池子内容占位（始终可聊）。
        for cat, pool in self._local_pools.items():
            existing = self.items.get(cat)
            if not existing:
                self.items[cat] = [dict(it, uid=_uid(it)) for it in pool]

    # ---- 更新 ----
    def update(self, category_items):
        """用最新抓取结果替换对应类别（空结果不覆盖，保留旧内容）。"""
        changed = False
        for cat, items in (category_items or {}).items():
            if not items:
                continue
            self.items[cat] = items[: self._max_items]
            changed = True
        if changed:
            self.refreshed_at = int(time.time())
            self.save()
        return changed

    # ---- 挑选 ----
    def pick(self, category):
        """从某类别挑一条尽量没聊过的条目；没有内容返回 ``None``。"""
        pool = self._pool(category)
        if not pool:
            return None
        unused = [it for it in pool if _uid(it) not in self._used]
        if not unused:
            # 全部聊过：清掉该类别的“已聊”标记，允许循环复用。
            for it in pool:
                self._forget(_uid(it))
            unused = list(pool)
        return random.choice(unused)

    def _pool(self, category):
        items = self.items.get(category)
        if items:
            return items
        return self._local_pools.get(category, [])

    def has_content(self, category):
        return bool(self._pool(category))

    def any_content(self, categories):
        return any(self.has_content(c) for c in categories)

    # ---- 已聊标记 ----
    def mark_used(self, item):
        uid = _uid(item)
        if not uid:
            return
        if uid in self._used:
            self._used_order.remove(uid)
        else:
            self._used.add(uid)
        self._used_order.append(uid)
        # 超出上限时丢弃最旧的记录。
        while len(self._used_order) > self._used_limit:
            old = self._used_order.pop(0)
            self._used.discard(old)
        self.save()

    def _forget(self, uid):
        if uid in self._used:
            self._used.discard(uid)
            try:
                self._used_order.remove(uid)
            except ValueError:
                pass

    # ---- 持久化 ----
    def save(self):
        save_json(self.path, {
            "items": self.items,
            "used_uids": self._used_order,
            "refreshed_at": self.refreshed_at,
        })
