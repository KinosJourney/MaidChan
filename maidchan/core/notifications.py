# -*- coding: utf-8 -*-
"""通知管理器：统一角色的对外表达（气泡）。

原本 ``say`` / ``show_local`` 直接操作 ``SpeechBubble``，而气泡回调又直接改
角色图片。这里把「说话通道」收敛到一处：

- 对外提供 ``show`` / ``show_error``，其它功能只管把要说的话交进来；
- 气泡的逐字 / 一句完成 / 全部完成回调统一转发给状态机，由状态机决定嘴巴动画；
- 预留 ``priority``：将来日程提醒等高优先级消息不应被普通闲聊顶掉。当前所有
  调用都用默认优先级 0，因此行为与旧版一致。
"""

from PySide6.QtCore import QObject


class NotificationManager(QObject):
    def __init__(self, bubble, split_fn, position_cb, state_machine, tts=None,
                 parent=None):
        super().__init__(parent)
        self._bubble = bubble
        self._split = split_fn
        self._position = position_cb
        self._state = state_machine
        self._tts = tts
        self._current_priority = 0

        # 气泡回调统一在这里接管，转发给状态机。
        bubble.on_sentence_typing = self._on_typing
        bubble.on_sentence_done = self._on_sentence_done
        bubble.on_all_done = self._on_all_done
        bubble.on_geometry_changed = position_cb

    # ---- 对外接口 ----
    def show(self, text, record=False, priority=0, link=None, speak_text=None):
        """显示一段话（会自动拆句）。

        ``record`` 参数保留以兼容旧签名；历史记录仍由调用方（对话流程）负责，
        与旧版一致，这里不写入历史。``link`` 非空时气泡可点击打开浏览器（查证 / 看原文）。
        ``speak_text`` 是用于语音朗读的文本；仅当它非空时才发声，
        这样日语模式不会拿系统日语音色去念本地中文模板。
        """
        # 高优先级消息正在显示时，不被更低优先级的消息打断。
        if self._bubble.isVisible() and priority < self._current_priority:
            return
        self._current_priority = priority
        sentences = self._split(text)
        # 新一段话开始：先打断上一段可能仍在朗读的语音；有朗读文本时再念这一段。
        if self._tts is not None:
            self._tts.stop()
            if speak_text:
                self._tts.speak(speak_text)
        self._bubble.speak(sentences, link=link)
        self._position()

    def show_error(self, text):
        self.show(text, record=False)

    def is_busy(self):
        if self._bubble.isVisible():
            return True
        if self._tts is not None and self._tts.is_speaking():
            return True
        return False

    # ---- 气泡回调 -> 状态机 ----
    def _on_typing(self):
        self._state.begin_speaking()

    def _on_sentence_done(self):
        self._state.end_sentence()

    def _on_all_done(self):
        self._state.end_speaking()
        self._current_priority = 0
