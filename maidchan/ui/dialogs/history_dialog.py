# -*- coding: utf-8 -*-
"""历史记录面板。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QWidget,
    QMessageBox,
)

from ...storage.history import HistoryStore


class HistoryDialog(QDialog):
    def __init__(self, history: HistoryStore, on_changed, parent=None):
        super().__init__(parent)
        self.history = history
        self.on_changed = on_changed
        self.setWindowTitle("历史记录")
        self.resize(560, 620)

        layout = QVBoxLayout(self)

        title = QLabel("与 Maid 的全部对话（删除后角色将不再记得这条内容）")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("清空全部")
        clear_btn.clicked.connect(self._clear_all)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        # 清空旧行
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.history.items:
            empty = QLabel("还没有任何对话记录～")
            empty.setAlignment(Qt.AlignCenter)
            self.vbox.addWidget(empty)
            return

        for it in reversed(self.history.items):
            row = QFrame()
            row.setStyleSheet(
                "QFrame { border-bottom: 1px solid #eee; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 6, 4, 6)

            who = "你" if it.get("role") == "user" else "Maid"
            text = "[%s] %s\n%s" % (it.get("time", ""), who, it.get("content", ""))
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("border: none;")
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row_layout.addWidget(lbl, 1)

            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(64)
            del_btn.setStyleSheet("border: none; color: #c0392b;")
            del_btn.clicked.connect(
                lambda _=False, iid=it.get("id"): self._delete(iid)
            )
            row_layout.addWidget(del_btn, 0, Qt.AlignTop)

            self.vbox.addWidget(row)

    def _delete(self, item_id):
        if self.history.delete(item_id):
            self.refresh()
            if self.on_changed:
                self.on_changed()

    def _clear_all(self):
        ret = QMessageBox.question(
            self, "确认", "确定要清空全部聊天记录吗？此操作不可恢复。"
        )
        if ret == QMessageBox.Yes:
            self.history.clear()
            self.refresh()
            if self.on_changed:
                self.on_changed()
