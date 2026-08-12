# -*- coding: utf-8 -*-
"""御主档案面板。"""

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
)

from ...storage.profile import Profile


class ProfileDialog(QDialog):
    def __init__(self, profile: Profile, on_saved, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.on_saved = on_saved
        self.setWindowTitle("御主档案")
        self.resize(460, 380)

        layout = QVBoxLayout(self)
        tip = QLabel("填写你的信息，角色会永远记得『你是谁』以及『你们的关系』。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        form = QFormLayout()
        self.inputs = {}
        for key, label in Profile.FIELDS:
            edit = QLineEdit()
            edit.setText(self.profile.get(key))
            self.inputs[key] = edit
            form.addRow(label + "：", edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        new_data = {k: self.inputs[k].text().strip() for k, _ in Profile.FIELDS}
        self.profile.update(new_data)
        if self.on_saved:
            self.on_saved()
        self.accept()
