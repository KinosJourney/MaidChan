# -*- coding: utf-8 -*-
"""设置面板（含 System Prompt 编辑）。"""

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QMessageBox,
)

from ...config.constants import DEFAULT_SYSTEM_PROMPT
from ...storage.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, on_saved, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.on_saved = on_saved
        self.setWindowTitle("设置 · 人设")
        self.resize(560, 520)

        layout = QVBoxLayout(self)

        tip = QLabel(
            "在下面直接修改角色的性格、称呼、语言风格。\n"
            "点击『保存』后立即生效，并会重置短期对话上下文，无需重启。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.editor = QTextEdit()
        self.editor.setPlainText(self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        layout.addWidget(self.editor, 1)

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
        self.settings.set("system_prompt", new_prompt)
        if self.on_saved:
            self.on_saved()
        self.accept()
