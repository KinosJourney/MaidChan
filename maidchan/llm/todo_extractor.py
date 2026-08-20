# -*- coding: utf-8 -*-
"""从一句话里解析「待办事项 + 截止时间」。

语音识别得到文本后，用一次轻量 API 调用判断这句话是不是在安排一件带时间的事，
并把口语化的时间（如「下午三点」「明天早上八点半」）换算成绝对时间。
解析为待办后由桌宠直接创建；普通语音则自动作为聊天消息发送。
"""

import json
import traceback
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from ..config.constants import DATETIME_FMT, DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .api_key import get_deepseek_api_key

try:
    import requests
except ImportError:
    requests = None

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

EXTRACTION_PROMPT = """\
你是一个待办事项解析器。用户在跟桌面助手说话，你要判断这句话是不是在安排一件
「需要在某个具体时间去做、并希望被提醒」的事情，并给出绝对时间。

规则：
1. 只有当用户明确要做某事且能确定具体时间点时，is_todo 才为 true。
2. 单纯的闲聊、提问、感慨、没有时间的想法，is_todo 一律为 false。
3. due_at 必须是未来的绝对时间，格式严格为 "YYYY-MM-DD HH:MM:SS"（24 小时制）。
4. 根据「当前时间」把「今天/明天/后天/下午三点/晚上八点半」等口语换算成绝对时间。
5. 只说了日期没说时间时，默认设为当天 09:00:00；说「上午」默认 09:00，「下午」默认 15:00，
   「晚上」默认 20:00，「中午」默认 12:00。
6. content 用简洁的一句话概括要做的事，不要包含时间词，也不要加「提醒我」之类的前缀。
7. 无法确定具体时间时，is_todo 设为 false。

输出严格 JSON（不要加 markdown 包裹）：
{"is_todo": true, "content": "开会", "due_at": "2026-08-20 15:00:00"}
如果不是待办，输出：{"is_todo": false, "content": "", "due_at": ""}"""


class TodoParseWorker(QThread):
    """后台线程：解析一句话中的待办与时间。"""

    parsed = Signal(dict)   # {"is_todo": bool, "content": str, "due_at": str}
    failed = Signal(str)

    def __init__(self, text, now=None, parent=None):
        super().__init__(parent)
        self.text = text
        self.now = now or datetime.now()

    def run(self):
        if requests is None:
            self.failed.emit("缺少 requests 库")
            return
        api_key = get_deepseek_api_key()
        if not api_key:
            self.failed.emit("无 API Key")
            return

        now = self.now
        context = "当前时间：%s（%s）" % (
            now.strftime(DATETIME_FMT), _WEEKDAYS[now.weekday()],
        )
        messages = [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": "%s\n用户说：%s" % (context, self.text)},
        ]
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 200,
            "stream": False,
        }

        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30
            )
            if resp.status_code != 200:
                self.failed.emit("待办解析接口 %d" % resp.status_code)
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            print("[待办] 模型原始返回：%s" % content)
            result = self._normalize(self._parse_result(content))
            if result is None:
                self.failed.emit("待办解析返回格式异常")
                return
            self.parsed.emit(result)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit("待办解析出错：%s" % str(e)[:100])

    def _parse_result(self, text):
        """解析 JSON，兼容模型加了 markdown 包裹的情况。"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    def _normalize(self, data):
        """校验并归一化解析结果；含糊 / 过去时间视为非待办。"""
        if not isinstance(data, dict):
            return None
        if not data.get("is_todo"):
            return {"is_todo": False, "content": "", "due_at": ""}

        content = str(data.get("content", "")).strip()
        due_dt = self._parse_due(str(data.get("due_at", "")).strip())
        if due_dt is None:
            return {"is_todo": False, "content": "", "due_at": ""}

        if not content or due_dt <= self.now:
            return {"is_todo": False, "content": "", "due_at": ""}

        return {
            "is_todo": True,
            "content": content,
            "due_at": due_dt.strftime(DATETIME_FMT),
        }

    @staticmethod
    def _parse_due(due_raw):
        """容忍模型可能省略秒 / 用不同分隔符的情况，尽量解析出时间。"""
        if not due_raw:
            return None
        # 兼容 ISO8601 的 'T' 分隔符
        cleaned = due_raw.replace("T", " ").strip()
        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        )
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except (ValueError, TypeError):
                continue
        return None
