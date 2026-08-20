# -*- coding: utf-8 -*-
"""长期记忆存储。

记忆与聊天历史分离：历史记录「发生过什么」，记忆记录「她对你形成的认知」。
记忆按类型分为：
- profile: 稳定身份信息（喜好、习惯、工作等）
- preference: 口味、偏好、厌恶
- episode: 具体事件（带时间，会随时间衰减）
- relationship: 称呼变化、承诺、关系进展
- goal: 长期目标和计划
"""

import random
import time
from datetime import datetime, timedelta

from .json_io import load_json, save_json
from ..config.constants import MAX_MEMORY_TOTAL, MAX_MEMORY_CONTENT_LEN

# 记忆类型
MEMORY_TYPES = ("profile", "preference", "episode", "relationship", "goal")

# episode 类型记忆默认有效天数
EPISODE_DEFAULT_TTL_DAYS = 30


class MemoryStore:
    """管理长期记忆：增删改查、相关性检索、过期清理。"""

    def __init__(self, path):
        self.path = path
        self.items = load_json(path, [])
        if not isinstance(self.items, list):
            self.items = []

    # ---- 增 ----
    def add(self, memory_type, content, tags=None, importance=0.5,
            confidence=0.9, source_ids=None):
        """添加一条新记忆。返回记忆对象。

        - 内容超过 MAX_MEMORY_CONTENT_LEN 会被截断。
        - 总条数超过 MAX_MEMORY_TOTAL 时自动淘汰最不重要的旧记忆。
        """
        content = content[:MAX_MEMORY_CONTENT_LEN]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item = {
            "id": "mem_%d_%04d" % (int(time.time() * 1000), random.randint(0, 9999)),
            "type": memory_type,
            "content": content,
            "tags": tags or [],
            "importance": max(0.0, min(1.0, importance)),
            "confidence": max(0.0, min(1.0, confidence)),
            "created_at": now,
            "updated_at": now,
            "source_message_ids": source_ids or [],
            "recall_count": 0,
            "last_recalled_at": None,
            "enabled": True,
        }
        self.items.append(item)
        self._evict_if_over_limit()
        self.save()
        return item

    # ---- 删 ----
    def delete(self, memory_id):
        before = len(self.items)
        self.items = [m for m in self.items if m.get("id") != memory_id]
        if len(self.items) != before:
            self.save()
            return True
        return False

    def clear(self):
        self.items = []
        self.save()

    # ---- 改 ----
    def update_content(self, memory_id, new_content, new_tags=None):
        """更新记忆内容（用于合并重复信息）。"""
        for m in self.items:
            if m.get("id") == memory_id:
                m["content"] = new_content
                if new_tags is not None:
                    m["tags"] = new_tags
                m["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save()
                return True
        return False

    def mark_recalled(self, memory_id):
        """标记一条记忆被召回，更新计数和时间。"""
        for m in self.items:
            if m.get("id") == memory_id:
                m["recall_count"] = m.get("recall_count", 0) + 1
                m["last_recalled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save()
                return

    # ---- 查 ----
    def get_enabled(self):
        """返回所有启用的记忆。"""
        return [m for m in self.items if m.get("enabled", True)]

    def get_by_type(self, memory_type):
        return [m for m in self.get_enabled() if m.get("type") == memory_type]

    def search_by_tags(self, query_tags, limit=5):
        """通过标签交集检索相关记忆，按相关性排序。"""
        if not query_tags:
            return []
        query_set = set(t.lower() for t in query_tags)
        scored = []
        for m in self.get_enabled():
            mem_tags = set(t.lower() for t in m.get("tags", []))
            overlap = query_set & mem_tags
            if overlap:
                score = self._score_memory(m, len(overlap) / max(len(query_set), 1))
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def get_recent_important(self, limit=5):
        """获取近期最重要的记忆，用于 Maid 主动开话题时提供素材。"""
        enabled = self.get_enabled()
        if not enabled:
            return []
        scored = []
        for m in enabled:
            importance = m.get("importance", 0.5)
            time_w = self._time_weight(m)
            recall = min(m.get("recall_count", 0), 10) / 10.0
            score = importance * 0.4 + time_w * 0.4 + recall * 0.2
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def search_by_keywords(self, keywords, limit=5):
        """通过关键词匹配记忆内容和标签。"""
        if not keywords:
            return []
        kw_list = [k.lower() for k in keywords if k.strip()]
        scored = []
        for m in self.get_enabled():
            content_lower = m.get("content", "").lower()
            tags_lower = " ".join(m.get("tags", [])).lower()
            text = content_lower + " " + tags_lower
            hits = sum(1 for k in kw_list if k in text)
            if hits > 0:
                relevance = hits / max(len(kw_list), 1)
                score = self._score_memory(m, relevance)
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def _score_memory(self, memory, relevance):
        """综合评分：相关性 × 0.6 + 重要度 × 0.25 + 时间权重 × 0.15"""
        importance = memory.get("importance", 0.5)
        time_weight = self._time_weight(memory)
        return relevance * 0.6 + importance * 0.25 + time_weight * 0.15

    def _time_weight(self, memory):
        """时间衰减：越新的记忆权重越高，episode 类型衰减更快。"""
        try:
            updated = datetime.strptime(memory["updated_at"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            return 0.5
        days_ago = (datetime.now() - updated).total_seconds() / 86400
        if memory.get("type") == "episode":
            # episode 半衰期 7 天
            return max(0.0, 1.0 - days_ago / 14.0)
        else:
            # 稳定记忆半衰期 60 天
            return max(0.0, 1.0 - days_ago / 120.0)

    # ---- 容量控制 ----
    def _evict_if_over_limit(self):
        """当总条数超过上限时，淘汰评分最低的记忆直到回到上限内。

        淘汰优先级：importance 低 → 时间权重低 → recall_count 少。
        profile/relationship 类型有保护加分，不容易被淘汰。
        """
        if len(self.items) <= MAX_MEMORY_TOTAL:
            return
        scored = []
        for m in self.items:
            importance = m.get("importance", 0.5)
            time_w = self._time_weight(m)
            recall = min(m.get("recall_count", 0), 10) / 10.0
            # 稳定类型保护加分
            type_bonus = 0.3 if m.get("type") in ("profile", "relationship") else 0.0
            score = importance * 0.4 + time_w * 0.3 + recall * 0.1 + type_bonus * 0.2
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        self.items = [m for _, m in scored[:MAX_MEMORY_TOTAL]]

    # ---- 维护 ----
    def cleanup_expired(self, ttl_days=EPISODE_DEFAULT_TTL_DAYS):
        """清理过期的 episode 记忆（超过 ttl_days 且重要度较低）。"""
        now = datetime.now()
        cutoff = now - timedelta(days=ttl_days)
        before = len(self.items)
        kept = []
        for m in self.items:
            if m.get("type") == "episode" and m.get("importance", 0.5) < 0.7:
                try:
                    created = datetime.strptime(m["created_at"], "%Y-%m-%d %H:%M:%S")
                    if created < cutoff:
                        continue
                except (KeyError, ValueError):
                    pass
            kept.append(m)
        self.items = kept
        if len(self.items) != before:
            self.save()

    def deduplicate(self, new_content, new_type):
        """检查是否已存在相似记忆，返回 (is_duplicate, existing_memory_or_None)。

        简单实现：如果同类型记忆中有内容包含关系，视为重复。
        """
        for m in self.get_enabled():
            if m.get("type") != new_type:
                continue
            existing = m.get("content", "")
            if new_content in existing or existing in new_content:
                return True, m
        return False, None

    # ---- 持久化 ----
    def save(self):
        save_json(self.path, self.items)

    # ---- 导出 / 导入 ----
    def export_to(self, path):
        """导出全部记忆到指定路径。"""
        return save_json(path, self.items)

    def import_from(self, path):
        """从文件导入记忆（合并，跳过已有 id）。返回新增条数，-1 表示失败。"""
        data = load_json(path, None)
        if not isinstance(data, list):
            return -1
        existing_ids = {m.get("id") for m in self.items}
        added = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            if not item.get("content"):
                continue
            if item.get("id") in existing_ids:
                continue
            self.items.append(item)
            added += 1
        if added > 0:
            self.save()
        return added

    # ---- 每日自动备份 ----
    def auto_backup(self, backup_dir):
        """每日自动备份。如果今天尚未备份且有记忆数据，则创建备份文件。

        备份目录下按日期命名：memories-2026-08-19.json
        保留最近 30 天的备份，更早的自动删除。
        """
        import os
        if not self.items:
            return
        os.makedirs(backup_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        backup_file = os.path.join(backup_dir, "memories-%s.json" % today)
        if os.path.exists(backup_file):
            return  # 今天已备份
        save_json(backup_file, self.items)
        self._cleanup_old_backups(backup_dir, keep_days=30)

    def _cleanup_old_backups(self, backup_dir, keep_days=30):
        """删除超过 keep_days 天的备份文件。"""
        import os
        cutoff = datetime.now() - timedelta(days=keep_days)
        try:
            for fname in os.listdir(backup_dir):
                if not fname.startswith("memories-") or not fname.endswith(".json"):
                    continue
                date_str = fname[len("memories-"):-len(".json")]
                try:
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff:
                        os.remove(os.path.join(backup_dir, fname))
                except ValueError:
                    continue
        except OSError:
            pass

    # ---- 统计 ----
    @property
    def count(self):
        return len(self.items)

    @property
    def enabled_count(self):
        return len(self.get_enabled())
