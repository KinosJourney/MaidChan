# -*- coding: utf-8 -*-
"""从对话中提取值得长期记住的信息。

每轮对话结束后，用一次轻量 API 调用让模型判断是否包含新记忆。
为了省 Token，只发送当前轮的 user + assistant 消息。
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

EXTRACTION_PROMPT = """\
你是一个严谨的记忆提取器。根据以下对话，判断是否包含值得长期记住的用户信息。

最重要的原则——绝不编造：
- 只能提取「用户说」这一段里用户【明确、直接】陈述过的关于自己的事实。
- 「角色回复」一段仅作为理解上下文，绝对不能从角色（AI）说的话里提取任何用户信息，
  也不能因为角色这样回复就假设用户认可。
- 不要推断、脑补、夸大或补全用户没有明说的细节；宁可漏记，也不要记错。
- 如果只是你的猜测、可能性或言外之意，一律不记。

其它规则：
1. 只提取关于用户本人的稳定信息、偏好、重要事件、目标或关系变化。
2. 不要记录普通寒暄、临时需求（如"帮我查个天气"）和角色自己说的话。
3. 每条记忆的 content 必须能在「用户说」的原文里找到明确依据，用简洁中立的一句话陈述，
   不添加原文没有的信息。
4. 如果用户纠正了之前的信息，标记 should_update 为 true。
5. 如果本轮没有【用户明确陈述】的可记信息，返回 should_remember: false。
6. importance: 0.0~1.0，生日/过敏/重大事件 > 0.7，普通喜好 0.4~0.6，临时事件 0.2~0.4。
7. type 只能是以下之一：profile, preference, episode, relationship, goal。

输出严格 JSON（不要加 markdown 包裹）：
{
  "should_remember": true/false,
  "memories": [
    {
      "type": "preference",
      "content": "用户喜欢吃火鸡面",
      "tags": ["饮食", "辣味"],
      "importance": 0.5,
      "should_update": false,
      "update_hint": ""
    }
  ]
}

如果 should_remember 为 false，memories 为空数组。"""


class MemoryExtractWorker(QThread):
    """后台线程：从最近一轮对话中提取记忆。"""
    extracted = Signal(list)  # list of memory dicts
    failed = Signal(str)

    def __init__(self, user_msg, assistant_msg, parent=None):
        super().__init__(parent)
        self.user_msg = user_msg
        self.assistant_msg = assistant_msg

    def run(self):
        if requests is None:
            self.failed.emit("缺少 requests 库")
            return
        api_key = get_deepseek_api_key()
        if not api_key:
            self.failed.emit("无 API Key")
            return

        messages = [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": (
                f"用户说：{self.user_msg}\n"
                f"角色回复：{self.assistant_msg}"
            )},
        ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 300,
            "stream": False,
        }

        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30
            )
            if resp.status_code != 200:
                self.failed.emit("记忆提取接口 %d" % resp.status_code)
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            result = self._parse_result(content)
            if result is None:
                self.failed.emit("记忆提取返回格式异常")
                return
            if result.get("should_remember") and result.get("memories"):
                self.extracted.emit(result["memories"])
            else:
                self.extracted.emit([])
        except Exception as e:
            traceback.print_exc()
            self.failed.emit("记忆提取出错：%s" % str(e)[:100])

    def _parse_result(self, text):
        """尝试解析 JSON，兼容模型加了 markdown 包裹的情况。"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
