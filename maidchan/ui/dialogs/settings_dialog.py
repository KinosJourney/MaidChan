# -*- coding: utf-8 -*-
"""设置面板（含 System Prompt 编辑与合集播放）。"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QSpinBox,
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
    DEFAULT_VOICE_HOTKEY,
    PROACTIVE_CATEGORIES,
    PROACTIVE_CATEGORY_LABELS,
    PROACTIVE_CHAT_DAILY_LIMIT,
    PROACTIVE_CHAT_ENABLED_DEFAULT,
    PROACTIVE_CHAT_INTERVAL_MINUTES,
    PROACTIVE_CHAT_MIN_IDLE_MINUTES,
    PROACTIVE_CHAT_QUIET_END_HOUR,
    PROACTIVE_CHAT_QUIET_START_HOUR,
)
from ...playlist.hotkey import hotkey_display
from ...storage.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, on_saved, on_test_proactive=None,
                 parent=None):
        super().__init__(parent)
        self.settings = settings
        self.on_saved = on_saved
        self.on_test_proactive = on_test_proactive
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
            "按住 %s 可在任意应用中开始录音，松开后自动发送。\n"
            "语音输入需要 OpenAI 兼容的语音识别 API。\n"
            "支持 OpenAI / Groq / 硅基流动等，也可在 .env 中配置：\n"
            "STT_API_KEY / STT_BASE_URL / STT_MODEL"
            % hotkey_display(DEFAULT_VOICE_HOTKEY)
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

        self._build_proactive_section(layout)

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

    def _build_proactive_section(self, layout):
        sep = QLabel("─── 主动陪聊 ───")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: #c0a0b0; font-size: 12px; margin-top: 8px;")
        layout.addWidget(sep)

        self.proactive_enabled = QCheckBox(
            "空闲时（未使用番茄钟）主动找我聊新闻 / 八卦 / 哲学 / 稀奇知识"
        )
        self.proactive_enabled.setChecked(
            bool(self.settings.get(
                "proactive_chat_enabled", PROACTIVE_CHAT_ENABLED_DEFAULT))
        )
        layout.addWidget(self.proactive_enabled)

        note = QLabel(
            "新闻 / 八卦来自公开 RSS（逐条附带来源，需要联网）；"
            "哲学 / 稀奇知识来自本地精选话题池。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a6a73; font-size: 12px;")
        layout.addWidget(note)

        cat_row = QHBoxLayout()
        cat_row.addWidget(QLabel("聊些什么："))
        selected = self.settings.get(
            "proactive_chat_categories", list(PROACTIVE_CATEGORIES)
        )
        self.proactive_cat_boxes = {}
        for cat in PROACTIVE_CATEGORIES:
            box = QCheckBox(PROACTIVE_CATEGORY_LABELS.get(cat, cat))
            box.setChecked(cat in selected)
            self.proactive_cat_boxes[cat] = box
            cat_row.addWidget(box)
        cat_row.addStretch()
        layout.addLayout(cat_row)

        grid = QGridLayout()

        def _spin(minv, maxv, value, suffix):
            sp = QSpinBox()
            sp.setRange(minv, maxv)
            sp.setValue(int(value))
            if suffix:
                sp.setSuffix(suffix)
            return sp

        self.proactive_interval = _spin(
            5, 720,
            self.settings.get(
                "proactive_chat_interval_minutes", PROACTIVE_CHAT_INTERVAL_MINUTES),
            " 分钟",
        )
        self.proactive_idle = _spin(
            1, 240,
            self.settings.get(
                "proactive_chat_min_idle_minutes", PROACTIVE_CHAT_MIN_IDLE_MINUTES),
            " 分钟",
        )
        self.proactive_daily = _spin(
            1, 50,
            self.settings.get(
                "proactive_chat_daily_limit", PROACTIVE_CHAT_DAILY_LIMIT),
            " 次",
        )
        self.proactive_quiet_start = _spin(
            0, 23,
            self.settings.get(
                "proactive_chat_quiet_start", PROACTIVE_CHAT_QUIET_START_HOUR),
            " 点",
        )
        self.proactive_quiet_end = _spin(
            0, 23,
            self.settings.get(
                "proactive_chat_quiet_end", PROACTIVE_CHAT_QUIET_END_HOUR),
            " 点",
        )

        grid.addWidget(QLabel("最短间隔："), 0, 0)
        grid.addWidget(self.proactive_interval, 0, 1)
        grid.addWidget(QLabel("空闲至少："), 0, 2)
        grid.addWidget(self.proactive_idle, 0, 3)
        grid.addWidget(QLabel("每日上限："), 1, 0)
        grid.addWidget(self.proactive_daily, 1, 1)
        grid.addWidget(QLabel("免打扰："), 1, 2)
        quiet_row = QHBoxLayout()
        quiet_row.addWidget(self.proactive_quiet_start)
        quiet_row.addWidget(QLabel("至"))
        quiet_row.addWidget(self.proactive_quiet_end)
        grid.addLayout(quiet_row, 1, 3)
        layout.addLayout(grid)

        if self.on_test_proactive is not None:
            test_row = QHBoxLayout()
            self.proactive_test_btn = QPushButton("▶ 立即试聊一条（测试）")
            self.proactive_test_btn.setToolTip(
                "不受空闲 / 间隔 / 番茄钟限制，用当前勾选的类别马上试发一条"
            )
            self.proactive_test_btn.clicked.connect(self._on_test_proactive_clicked)
            test_row.addStretch()
            test_row.addWidget(self.proactive_test_btn)
            layout.addLayout(test_row)

    def _checked_categories(self):
        return [
            cat for cat, box in self.proactive_cat_boxes.items()
            if box.isChecked()
        ]

    def _on_test_proactive_clicked(self):
        if self.on_test_proactive is None:
            return
        self.on_test_proactive(self._checked_categories())

    def _save_proactive(self):
        self.settings.set(
            "proactive_chat_enabled", self.proactive_enabled.isChecked())
        self.settings.set(
            "proactive_chat_categories", self._checked_categories())
        self.settings.set(
            "proactive_chat_interval_minutes", self.proactive_interval.value())
        self.settings.set(
            "proactive_chat_min_idle_minutes", self.proactive_idle.value())
        self.settings.set(
            "proactive_chat_daily_limit", self.proactive_daily.value())
        self.settings.set(
            "proactive_chat_quiet_start", self.proactive_quiet_start.value())
        self.settings.set(
            "proactive_chat_quiet_end", self.proactive_quiet_end.value())

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

        self._save_proactive()

        if self.on_saved:
            self.on_saved(prompt_changed)
        self.accept()
