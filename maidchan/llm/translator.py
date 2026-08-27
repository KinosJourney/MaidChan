# -*- coding: utf-8 -*-
"""把角色的中文回复翻译成日语，供语音朗读使用。

日语朗读模式下，先照常显示中文气泡，再用一次轻量 API 调用把这段中文翻成
自然口语的日语，然后交给系统日语语音（Kyoko）朗读。翻译是明确任务，模型
遵守度远高于「在聊天里附带一行日语」，因此比同话请求可靠得多。
"""

from PySide6.QtCore import QThread, Signal

from ..config.constants import DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .api_key import get_deepseek_api_key

try:
    import requests
except ImportError:
    requests = None


_TRANSLATE_PROMPT = (
    "你是专业的中译日配音翻译。把用户给出的中文台词翻译成自然、口语化、"
    "适合朗读的日语。只输出日语译文本身，不要输出任何解释、罗马音、"
    "括号备注或多余内容。保留原句的语气与情感。"
)


class TranslateWorker(QThread):
    """后台线程：把一段中文翻译成日语。"""

    translated = Signal(str)
    failed = Signal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        if requests is None:
            self.failed.emit("缺少 requests 库")
            return
        api_key = get_deepseek_api_key()
        if not api_key:
            self.failed.emit("无 API Key")
            return

        messages = [
            {"role": "system", "content": _TRANSLATE_PROMPT},
            {"role": "user", "content": self.text},
        ]
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 256,
            "stream": False,
        }
        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30
            )
            if resp.status_code != 200:
                self.failed.emit("翻译接口 %d" % resp.status_code)
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if content:
                self.translated.emit(content)
            else:
                self.failed.emit("翻译返回为空")
        except Exception as e:
            self.failed.emit("翻译出错：%s" % str(e)[:100])
