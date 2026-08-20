# -*- coding: utf-8 -*-
"""设置面板（含 System Prompt 编辑与合集播放）。"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QMessageBox,
)

from ...config.constants import (
    DEFAULT_PLAYLIST_HOTKEY,
    DEFAULT_PLAYLIST_URL,
    DEFAULT_STT_BASE_URL,
    DEFAULT_SYSTEM_PROMPT,
)
from ...playlist.hotkey import hotkey_display
from ...storage.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, on_saved, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.on_saved = on_saved
        self.setWindowTitle("设置 · 人设")
        self.resize(560, 700)

        layout = QVBoxLayout(self)

        tip = QLabel(
            "在下面直接修改角色的性格、称呼、语言风格。\n"
            "点击『保存』后立即生效；若人设有改动，会重置短期对话上下文，无需重启。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.editor = QTextEdit()
        self.editor.setPlainText(self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        layout.addWidget(self.editor, 1)

        playlist_tip = QLabel(
            "B 站合集链接（快捷键 %s 随机播放其中一条）："
            % hotkey_display(DEFAULT_PLAYLIST_HOTKEY)
        )
        playlist_tip.setWordWrap(True)
        layout.addWidget(playlist_tip)
        self.playlist_edit = QLineEdit()
        self.playlist_edit.setText(
            self.settings.get("playlist_url", DEFAULT_PLAYLIST_URL)
        )
        self.playlist_edit.setPlaceholderText(DEFAULT_PLAYLIST_URL)
        layout.addWidget(self.playlist_edit)
        if sys.platform == "darwin":
            note = QLabel("提示：快捷键是 Control+Shift+P，不是 Command。")
            note.setStyleSheet("color: #8a6a73; font-size: 12px;")
            layout.addWidget(note)

        # ─── 语音输入设置 ───
        stt_sep = QLabel("─── 语音输入 ───")
        stt_sep.setAlignment(Qt.AlignCenter)
        stt_sep.setStyleSheet("color: #c0a0b0; font-size: 12px; margin-top: 8px;")
        layout.addWidget(stt_sep)

        stt_tip = QLabel(
            "语音按钮需要 OpenAI 兼容的语音识别 API。\n"
            "支持 OpenAI / Groq / 硅基流动等，也可在 .env 中配置：\n"
            "STT_API_KEY / STT_BASE_URL / STT_MODEL"
        )
        stt_tip.setWordWrap(True)
        stt_tip.setStyleSheet("color: #8a6a73; font-size: 12px;")
        layout.addWidget(stt_tip)

        self.stt_key_edit = QLineEdit()
        self.stt_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.stt_key_edit.setText(self.settings.get("stt_api_key", ""))
        self.stt_key_edit.setPlaceholderText("语音识别 API Key（留空则使用 .env）")
        layout.addWidget(self.stt_key_edit)

        self.stt_url_edit = QLineEdit()
        self.stt_url_edit.setText(self.settings.get("stt_base_url", ""))
        self.stt_url_edit.setPlaceholderText(
            "API 地址，如 %s（留空则使用 .env）" % DEFAULT_STT_BASE_URL
        )
        layout.addWidget(self.stt_url_edit)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认人设")
        reset_btn.clicked.connect(self._reset)
        save_btn = QPushButton("保存并生效")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _reset(self):
        self.editor.setPlainText(DEFAULT_SYSTEM_PROMPT)

    def _save(self):
        new_prompt = self.editor.toPlainText().strip()
        if not new_prompt:
            QMessageBox.warning(self, "提示", "人设不能为空哦～")
            return
        new_url = self.playlist_edit.text().strip() or DEFAULT_PLAYLIST_URL
        if not (new_url.startswith("http://") or new_url.startswith("https://")):
            QMessageBox.warning(self, "提示", "合集链接需要以 http:// 或 https:// 开头。")
            return

        old_prompt = self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        prompt_changed = new_prompt != old_prompt
        self.settings.set("system_prompt", new_prompt)
        self.settings.set("playlist_url", new_url)

        self.settings.set("stt_api_key", self.stt_key_edit.text().strip())
        stt_url = self.stt_url_edit.text().strip()
        self.settings.set("stt_base_url", stt_url)

        if self.on_saved:
            self.on_saved(prompt_changed)
        self.accept()
