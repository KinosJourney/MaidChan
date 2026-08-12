# -*- coding: utf-8 -*-
"""DeepSeek 后台请求线程（避免卡住界面）。"""

from PySide6.QtCore import QThread, Signal

from ..config.constants import DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .api_key import get_deepseek_api_key

try:
    import requests
except ImportError:
    requests = None  # 会在调用时给出提示


class ChatWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, messages, parent=None):
        super().__init__(parent)
        self.messages = messages

    def run(self):
        if requests is None:
            self.failed.emit("缺少 requests 库，请先运行 install 脚本安装依赖。")
            return

        api_key = get_deepseek_api_key()
        if not api_key:
            self.failed.emit(
                "未找到 DeepSeek API Key。请在程序目录的 .env 文件中配置后重新启动。"
            )
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": self.messages,
            "temperature": 1.0,
            "max_tokens": 512,
            "stream": False,
        }
        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=45
            )
            if resp.status_code == 401:
                self.failed.emit("API Key 无效（401），请检查你填写的 Key 是否正确。")
                return
            if resp.status_code == 402:
                self.failed.emit("账户余额不足（402），请到 DeepSeek 平台充值。")
                return
            if resp.status_code != 200:
                self.failed.emit("接口返回错误 %s：%s" % (resp.status_code, resp.text[:120]))
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if not content:
                content = "……（我一时语塞了）"
            self.finished_ok.emit(content)
        except requests.exceptions.Timeout:
            self.failed.emit("网络超时了，请稍后再试～")
        except requests.exceptions.ConnectionError:
            self.failed.emit("连不上网络，请检查你的网络连接。")
        except Exception as e:
            self.failed.emit("出错了：%s" % str(e)[:150])
