# -*- coding: utf-8 -*-
"""待办事项面板与编辑/确认表单。

- ``TodoEditDialog``：新建 / 编辑单条待办的模态表单，保存时校验内容非空、
  时间在未来。
- ``TodoListDialog``：待办清单，按「未完成 / 已完成」分组展示，支持新增、编辑、
  完成 / 恢复、删除。
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...config.constants import DATETIME_FMT
from ...storage.todo import STATUS_DONE, parse_dt

_ACTIVE_BTN = (
    "QPushButton {"
    "  background: #ffb7c5; color: white; border: none;"
    "  border-radius: 12px; padding: 6px 18px; font-size: 13px; font-weight: bold;"
    "}"
    "QPushButton:hover { background: #ff9db0; }"
)


class TodoEditDialog(QDialog):
    """新建 / 确认 / 编辑一条待办。"""

    def __init__(self, content="", due_dt=None, title="新建待办", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(340)
        # 桌宠窗口是置顶的，确认框也必须置顶，否则会被挡在后面看不见。
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.content_value = ""
        self.due_value = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("要做的事："))
        self._content_edit = QLineEdit(content)
        self._content_edit.setPlaceholderText("例如：开组会 / 吃药 / 给妈妈打电话")
        self._content_edit.setStyleSheet(
            "QLineEdit {"
            "  border: 2px solid #ffb7c5; border-radius: 10px;"
            "  padding: 6px 10px; font-size: 13px;"
            "}"
        )
        layout.addWidget(self._content_edit)

        layout.addWidget(QLabel("提醒时间："))
        self._dt_edit = QDateTimeEdit()
        self._dt_edit.setCalendarPopup(True)
        self._dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        if due_dt is None:
            # 默认下一个整十分钟后，避免默认时间已过期
            due_dt = (datetime.now() + timedelta(minutes=10)).replace(second=0, microsecond=0)
        self._dt_edit.setDateTime(QDateTime(due_dt))
        self._dt_edit.setStyleSheet("padding: 4px 6px; font-size: 13px;")
        layout.addWidget(self._dt_edit)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("保存")
        ok_btn.setStyleSheet(_ACTIVE_BTN)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _on_ok(self):
        content = self._content_edit.text().strip()
        if not content:
            QMessageBox.warning(self, "提示", "请先填写要做的事情哦～")
            return
        due = self._dt_edit.dateTime().toPython()
        if not isinstance(due, datetime):
            due = datetime.fromtimestamp(self._dt_edit.dateTime().toSecsSinceEpoch())
        due = due.replace(second=0, microsecond=0)
        if due <= datetime.now():
            QMessageBox.warning(self, "提示", "提醒时间要设在将来才行呀～")
            return
        self.content_value = content
        self.due_value = due
        self.accept()


class TodoListDialog(QDialog):
    """待办清单：新增 / 编辑 / 完成 / 删除。"""

    def __init__(self, store, on_changed=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.on_changed = on_changed
        self.setWindowTitle("待办事项")
        self.resize(520, 620)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        title = QLabel("需要提醒的待办事项。到点前会提前提醒你，记得让我一直开着哦～")
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
        add_btn = QPushButton("新增待办")
        add_btn.setStyleSheet(_ACTIVE_BTN)
        add_btn.clicked.connect(self._add)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.refresh()

    # ---- 列表渲染 ----
    def refresh(self):
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        pending = self.store.sorted_pending()
        done = self.store.done()

        if not pending and not done:
            empty = QLabel("还没有待办事项～说一句「提醒我下午三点开会」试试吧！")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #999; padding: 40px;")
            self.vbox.addWidget(empty)
            return

        if pending:
            self.vbox.addWidget(self._section_label("未完成（%d）" % len(pending)))
            for t in pending:
                self.vbox.addWidget(self._build_row(t, done=False))
        if done:
            self.vbox.addWidget(self._section_label("已完成（%d）" % len(done)))
            for t in done:
                self.vbox.addWidget(self._build_row(t, done=True))

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #e85d75; font-weight: bold; font-size: 13px; padding: 8px 2px 2px;"
        )
        return lbl

    def _build_row(self, todo, done):
        row = QFrame()
        row.setStyleSheet("QFrame { border-bottom: 1px solid #f0f0f0; }")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 8, 6, 8)
        row_layout.setSpacing(8)

        info = QVBoxLayout()
        info.setSpacing(2)
        content = todo.get("content", "")
        content_lbl = QLabel(content)
        content_lbl.setWordWrap(True)
        content_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        if done:
            content_lbl.setStyleSheet(
                "border: none; font-size: 14px; color: #aaa; text-decoration: line-through;"
            )
        else:
            content_lbl.setStyleSheet("border: none; font-size: 14px; color: #3a2b35;")
        info.addWidget(content_lbl)

        due_lbl = QLabel(self._due_text(todo))
        due_lbl.setStyleSheet("border: none; font-size: 12px; color: #999;")
        info.addWidget(due_lbl)
        row_layout.addLayout(info, 1)

        todo_id = todo.get("id")
        if not done:
            done_btn = QPushButton("完成")
            done_btn.setFixedWidth(56)
            done_btn.setStyleSheet("border: none; color: #27ae60; font-weight: bold;")
            done_btn.clicked.connect(lambda _=False, i=todo_id: self._complete(i))
            row_layout.addWidget(done_btn, 0, Qt.AlignTop)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedWidth(56)
            edit_btn.setStyleSheet("border: none; color: #3498db;")
            edit_btn.clicked.connect(lambda _=False, i=todo_id: self._edit(i))
            row_layout.addWidget(edit_btn, 0, Qt.AlignTop)
        else:
            restore_btn = QPushButton("恢复")
            restore_btn.setFixedWidth(56)
            restore_btn.setStyleSheet("border: none; color: #e67e22;")
            restore_btn.clicked.connect(lambda _=False, i=todo_id: self._restore(i))
            row_layout.addWidget(restore_btn, 0, Qt.AlignTop)

        del_btn = QPushButton("删除")
        del_btn.setFixedWidth(56)
        del_btn.setStyleSheet("border: none; color: #c0392b;")
        del_btn.clicked.connect(lambda _=False, i=todo_id: self._delete(i))
        row_layout.addWidget(del_btn, 0, Qt.AlignTop)

        return row

    def _due_text(self, todo):
        due = parse_dt(todo.get("due_at"))
        if due is None:
            return "时间未设置"
        text = due.strftime("%Y-%m-%d %H:%M")
        if todo.get("status") != STATUS_DONE and due < datetime.now():
            text += "（已过期）"
        return text

    # ---- 操作 ----
    def _notify_changed(self):
        if self.on_changed:
            self.on_changed()

    def _add(self):
        dlg = TodoEditDialog(title="新建待办", parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.store.add(dlg.content_value, dlg.due_value, source="manual")
            self.refresh()
            self._notify_changed()

    def _edit(self, todo_id):
        todo = self.store.get(todo_id)
        if todo is None:
            return
        dlg = TodoEditDialog(
            content=todo.get("content", ""),
            due_dt=parse_dt(todo.get("due_at")),
            title="编辑待办",
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            self.store.update(todo_id, content=dlg.content_value, due_at=dlg.due_value)
            self.refresh()
            self._notify_changed()

    def _complete(self, todo_id):
        self.store.mark_done(todo_id)
        self.refresh()
        self._notify_changed()

    def _restore(self, todo_id):
        self.store.mark_pending(todo_id)
        self.refresh()
        self._notify_changed()

    def _delete(self, todo_id):
        if self.store.delete(todo_id):
            self.refresh()
            self._notify_changed()
