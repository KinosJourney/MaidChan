# -*- coding: utf-8 -*-
"""根据当前用户消息，从长期记忆中检索最相关的记忆。

第一版使用轻量 API 调用提取关键词，再匹配记忆库。
未来可替换为向量检索。
"""

import json
import traceback

from PySide6.QtCore import QThread, Signal

from ..config.constants import DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .api_key import get_deepseek_api_key

try:
    import requests
except ImportError:
    requests = None

KEYWORD_PROMPT = """\
从用户消息中提取 1~5 个与用户本人相关的关键词/标签，用于检索长期记忆。
只关注：饮食、健康、情绪、工作、学习、人际、兴趣、计划等与用户相关的方面。
如果消息是纯闲聊/打招呼/无个人信息，返回空数组。

输出严格 JSON（不要加 markdown 包裹）：
{"keywords": ["关键词1", "关键词2"]}"""


class KeywordExtractWorker(QThread):
    """从用户消息提取关键词，用于记忆检索。"""
    extracted = Signal(list)  # list of keyword strings
    failed = Signal(str)

    def __init__(self, user_msg, parent=None):
        super().__init__(parent)
        self.user_msg = user_msg

    def run(self):
        if requests is None:
            self.extracted.emit([])
            return
        api_key = get_deepseek_api_key()
        if not api_key:
            self.extracted.emit([])
            return

        messages = [
            {"role": "system", "content": KEYWORD_PROMPT},
            {"role": "user", "content": self.user_msg},
        ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 100,
            "stream": False,
        }

        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=15
            )
            if resp.status_code != 200:
                self.extracted.emit([])
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            result = self._parse(content)
            self.extracted.emit(result)
        except Exception:
            traceback.print_exc()
            self.extracted.emit([])

    def _parse(self, text):
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            obj = json.loads(text)
            kw = obj.get("keywords", [])
            if isinstance(kw, list):
                return [str(k) for k in kw if k]
            return []
        except json.JSONDecodeError:
            return []


def retrieve_memories_sync(memory_store, keywords, limit=5):
    """同步检索：根据关键词从记忆库检索最相关的记忆。

    这是一个纯本地操作（不调 API），可以在主线程安全调用。
    """
    if not keywords:
        return []
    return memory_store.search_by_keywords(keywords, limit=limit)


def format_memories_for_prompt(memories):
    """将检索到的记忆格式化为注入 system prompt 的文本。"""
    if not memories:
        return ""
    lines = ["【可能相关的记忆（仅在与当前话题直接相关时才自然融入回答，不要主动罗列或强行关联）】"]
    for m in memories:
        content = m.get("content", "")
        mem_type = m.get("type", "")
        created = m.get("created_at", "")[:10]
        if mem_type == "episode":
            lines.append(f"- [{created}] {content}")
        else:
            lines.append(f"- {content}")
    lines.append("")
    return "\n".join(lines)
