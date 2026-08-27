# -*- coding: utf-8 -*-
"""设置面板（含 System Prompt 编辑与合集播放）。"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
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
    TTS_ENABLED_DEFAULT,
    TTS_API_URL_DEFAULTS,
    TTS_LANG_DEFAULT,
    TTS_PROMPT_LANG_DEFAULT,
    TTS_PROVIDER_DEFAULT,
    TTS_RATE_DEFAULT,
    TTS_REF_AUDIO_DEFAULT,
    TTS_REF_TEXT_DEFAULT,
    TTS_VOICE_DEFAULT,
    TTS_VOLUME_DEFAULT,
)
from ...playlist.hotkey import hotkey_display
from ...storage.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, on_saved, on_test_proactive=None,
                 on_preview_tts=None, tts_available=True, voices_getter=None,
                 parent=None):
        super().__init__(parent)
        self.settings = settings
        self.on_saved = on_saved
        self.on_test_proactive = on_test_proactive
        self.on_preview_tts = on_preview_tts
        self._tts_available = tts_available
        # voices_getter(lang) -> [音色名]；用于按语言填充音色下拉。
        self._voices_getter = voices_getter or (lambda lang: [])
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

        self._build_tts_section(layout)

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

    def _build_tts_section(self, layout):
        sep = QLabel("─── 语音朗读 ───")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: #c0a0b0; font-size: 12px; margin-top: 8px;")
        layout.addWidget(sep)

        self.tts_enabled = QCheckBox("开启后，我会把回复念出来（气泡始终显示中文）")
        self.tts_enabled.setChecked(
            bool(self.settings.get("tts_enabled", TTS_ENABLED_DEFAULT))
        )
        layout.addWidget(self.tts_enabled)

        note = QLabel(
            "可使用系统语音，或连接 GPT-SoVITS / CosyVoice 本地 HTTP 服务。\n"
            "· 日语：气泡显示中文，回复会多生成一句日语用于朗读；\n"
            "· 中文：直接朗读气泡里的中文（问候 / 提醒也会念）。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a6a73; font-size: 12px;")
        layout.addWidget(note)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("语音后端："))
        self.tts_provider = QComboBox()
        self.tts_provider.addItem("系统语音", "system")
        self.tts_provider.addItem("GPT-SoVITS", "gpt-sovits")
        self.tts_provider.addItem("CosyVoice", "cosyvoice")
        current_provider = self.settings.get(
            "tts_provider", TTS_PROVIDER_DEFAULT
        )
        idx = self.tts_provider.findData(current_provider)
        self.tts_provider.setCurrentIndex(idx if idx >= 0 else 0)
        provider_row.addWidget(self.tts_provider)
        provider_row.addStretch()
        layout.addLayout(provider_row)

        self.tts_api_url = QLineEdit()
        self.tts_api_url.setText(self.settings.get(
            "tts_api_url", TTS_API_URL_DEFAULTS.get(current_provider, "")
        ))
        self.tts_api_url.setPlaceholderText("TTS 服务地址")
        layout.addWidget(self.tts_api_url)

        ref_row = QHBoxLayout()
        self.tts_ref_audio = QLineEdit()
        self.tts_ref_audio.setText(self.settings.get(
            "tts_ref_audio", TTS_REF_AUDIO_DEFAULT
        ))
        self.tts_ref_audio.setPlaceholderText(
            "角色参考音频（GPT-SoVITS 填服务端可见路径）"
        )
        ref_btn = QPushButton("选择…")
        ref_btn.clicked.connect(self._choose_tts_ref_audio)
        ref_row.addWidget(self.tts_ref_audio, 1)
        ref_row.addWidget(ref_btn)
        layout.addLayout(ref_row)
        self.tts_ref_btn = ref_btn

        self.tts_ref_text = QTextEdit()
        self.tts_ref_text.setMaximumHeight(62)
        self.tts_ref_text.setPlainText(self.settings.get(
            "tts_ref_text", TTS_REF_TEXT_DEFAULT
        ))
        self.tts_ref_text.setPlaceholderText("参考音频对应的原文")
        layout.addWidget(self.tts_ref_text)

        prompt_row = QHBoxLayout()
        prompt_row.addWidget(QLabel("参考音频语言："))
        self.tts_prompt_lang = QComboBox()
        self.tts_prompt_lang.addItem("日语", "ja")
        self.tts_prompt_lang.addItem("中文", "zh")
        prompt_lang = self.settings.get(
            "tts_prompt_lang", TTS_PROMPT_LANG_DEFAULT
        )
        idx = self.tts_prompt_lang.findData(prompt_lang)
        self.tts_prompt_lang.setCurrentIndex(idx if idx >= 0 else 0)
        prompt_row.addWidget(self.tts_prompt_lang)
        prompt_row.addStretch()
        layout.addLayout(prompt_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("朗读语言："))
        self.tts_lang = QComboBox()
        self.tts_lang.addItem("日语（Kyoko）", "ja")
        self.tts_lang.addItem("中文（Tingting）", "zh")
        cur_lang = self.settings.get("tts_lang", TTS_LANG_DEFAULT)
        idx = self.tts_lang.findData(cur_lang)
        self.tts_lang.setCurrentIndex(idx if idx >= 0 else 0)
        lang_row.addWidget(self.tts_lang)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("音色："))
        self.tts_voice = QComboBox()
        voice_row.addWidget(self.tts_voice)
        voice_row.addStretch()
        layout.addLayout(voice_row)
        # 先按当前语言填充音色，再监听语言切换刷新（放在填充后避免触发时控件未就绪）。
        self._populate_voices(cur_lang, self.settings.get("tts_voice", TTS_VOICE_DEFAULT))
        self.tts_lang.currentIndexChanged.connect(self._on_lang_changed)

        self.tts_system_warn = QLabel(
            "当前系统未检测到可用的语音引擎，可改用角色声线服务。"
        )
        self.tts_system_warn.setWordWrap(True)
        self.tts_system_warn.setStyleSheet(
            "color: #a33a3a; font-size: 12px;"
        )
        layout.addWidget(self.tts_system_warn)

        grid = QGridLayout()

        # 音量 0~100 -> 0.0~1.0
        self.tts_volume = QSlider(Qt.Horizontal)
        self.tts_volume.setRange(0, 100)
        self.tts_volume.setValue(
            int(float(self.settings.get("tts_volume", TTS_VOLUME_DEFAULT)) * 100)
        )
        # 语速 -100~100 -> -1.0~1.0
        self.tts_rate = QSlider(Qt.Horizontal)
        self.tts_rate.setRange(-100, 100)
        self.tts_rate.setValue(
            int(float(self.settings.get("tts_rate", TTS_RATE_DEFAULT)) * 100)
        )

        grid.addWidget(QLabel("音量："), 0, 0)
        grid.addWidget(self.tts_volume, 0, 1)
        grid.addWidget(QLabel("语速："), 1, 0)
        grid.addWidget(self.tts_rate, 1, 1)
        layout.addLayout(grid)

        if self.on_preview_tts is not None:
            row = QHBoxLayout()
            preview_btn = QPushButton("▶ 试听")
            preview_btn.clicked.connect(self._on_preview_tts_clicked)
            row.addStretch()
            row.addWidget(preview_btn)
            layout.addLayout(row)

        self.tts_provider.currentIndexChanged.connect(
            self._on_tts_provider_changed
        )
        self._update_tts_provider_fields()

    def _tts_volume_value(self):
        return round(self.tts_volume.value() / 100.0, 2)

    def _tts_rate_value(self):
        return round(self.tts_rate.value() / 100.0, 2)

    def _tts_lang_value(self):
        return self.tts_lang.currentData() or TTS_LANG_DEFAULT

    def _tts_voice_value(self):
        return self.tts_voice.currentData() or ""

    def _tts_provider_value(self):
        return self.tts_provider.currentData() or TTS_PROVIDER_DEFAULT

    def _tts_config_values(self):
        return {
            "provider": self._tts_provider_value(),
            "api_url": self.tts_api_url.text().strip(),
            "ref_audio": self.tts_ref_audio.text().strip(),
            "ref_text": self.tts_ref_text.toPlainText().strip(),
            "prompt_lang": (
                self.tts_prompt_lang.currentData()
                or TTS_PROMPT_LANG_DEFAULT
            ),
        }

    def _populate_voices(self, lang, selected=""):
        """按语言填充音色下拉：首项为「自动」，其余为系统可用音色。"""
        self.tts_voice.blockSignals(True)
        self.tts_voice.clear()
        self.tts_voice.addItem("自动（默认音色）", "")
        for name in self._voices_getter(lang):
            self.tts_voice.addItem(name, name)
        idx = self.tts_voice.findData(selected) if selected else 0
        self.tts_voice.setCurrentIndex(idx if idx >= 0 else 0)
        self.tts_voice.setEnabled(
            self._tts_provider_value() == "system"
            and self._tts_available
            and self.tts_voice.count() > 1
        )
        self.tts_voice.blockSignals(False)

    def _choose_tts_ref_audio(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "选择角色参考音频", "", "音频文件 (*.wav *.mp3 *.flac *.m4a)"
        )
        if path:
            self.tts_ref_audio.setText(path)

    def _on_tts_provider_changed(self, _idx):
        provider = self._tts_provider_value()
        known_defaults = set(TTS_API_URL_DEFAULTS.values())
        current_url = self.tts_api_url.text().strip()
        if not current_url or current_url in known_defaults:
            self.tts_api_url.setText(TTS_API_URL_DEFAULTS.get(provider, ""))
        self._update_tts_provider_fields()

    def _update_tts_provider_fields(self):
        is_system = self._tts_provider_value() == "system"
        for widget in (
            self.tts_api_url,
            self.tts_ref_audio,
            self.tts_ref_btn,
            self.tts_ref_text,
            self.tts_prompt_lang,
        ):
            widget.setEnabled(not is_system)
        self.tts_voice.setEnabled(
            is_system and self._tts_available and self.tts_voice.count() > 1
        )
        self.tts_system_warn.setVisible(is_system and not self._tts_available)

    def _on_lang_changed(self, _idx):
        # 切换语言后音色列表随之变化，旧音色多半不属于新语言，重置为自动。
        self._populate_voices(self._tts_lang_value(), selected="")

    def _on_preview_tts_clicked(self):
        if self.on_preview_tts is None:
            return
        values = self._tts_config_values()
        values.update({
            "volume": self._tts_volume_value(),
            "rate": self._tts_rate_value(),
            "lang": self._tts_lang_value(),
            "voice": self._tts_voice_value(),
        })
        self.on_preview_tts(values)

    def _save_tts(self):
        self.settings.set("tts_enabled", self.tts_enabled.isChecked())
        self.settings.set("tts_volume", self._tts_volume_value())
        self.settings.set("tts_rate", self._tts_rate_value())
        self.settings.set("tts_lang", self._tts_lang_value())
        self.settings.set("tts_voice", self._tts_voice_value())
        values = self._tts_config_values()
        self.settings.set("tts_provider", values["provider"])
        self.settings.set("tts_api_url", values["api_url"])
        self.settings.set("tts_ref_audio", values["ref_audio"])
        self.settings.set("tts_ref_text", values["ref_text"])
        self.settings.set("tts_prompt_lang", values["prompt_lang"])

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
        tts_config = self._tts_config_values()
        if self.tts_enabled.isChecked() and tts_config["provider"] != "system":
            if not tts_config["api_url"].startswith(("http://", "https://")):
                QMessageBox.warning(self, "提示", "TTS 服务地址需要以 http:// 或 https:// 开头。")
                return
            if not tts_config["ref_audio"] or not tts_config["ref_text"]:
                QMessageBox.warning(self, "提示", "角色声线需要参考音频和对应原文。")
                return
            if (
                tts_config["provider"] == "cosyvoice"
                and not os.path.isfile(tts_config["ref_audio"])
            ):
                QMessageBox.warning(self, "提示", "CosyVoice 参考音频文件不存在。")
                return

        old_prompt = self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        prompt_changed = new_prompt != old_prompt
        self.settings.set("system_prompt", new_prompt)
        self.settings.set("playlist_url", new_url)

        self.settings.set("stt_api_key", self.stt_key_edit.text().strip())
        stt_url = self.stt_url_edit.text().strip()
        self.settings.set("stt_base_url", stt_url)

        self._save_tts()

        self._save_proactive()

        if self.on_saved:
            self.on_saved(prompt_changed)
        self.accept()
