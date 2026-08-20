# -*- coding: utf-8 -*-
"""长期记忆管理面板。"""

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
    QComboBox,
    QFileDialog,
)

from ...storage.memory import MemoryStore

_TYPE_LABELS = {
    "profile": "身份信息",
    "preference": "偏好",
    "episode": "事件经历",
    "relationship": "关系",
    "goal": "目标计划",
}

_TYPE_COLORS = {
    "profile": "#3498db",
    "preference": "#e67e22",
    "episode": "#9b59b6",
    "relationship": "#e91e63",
    "goal": "#27ae60",
}


class MemoryDialog(QDialog):
    def __init__(self, memory: MemoryStore, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setWindowTitle("长期记忆")
        self.resize(580, 640)

        layout = QVBoxLayout(self)

        # 标题和说明
        title = QLabel(
            "Maid 对你形成的长期认知。删除后她将彻底忘记对应内容。"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        # 筛选栏
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("筛选："))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("全部", "")
        for type_key, type_label in _TYPE_LABELS.items():
            self.filter_combo.addItem(type_label, type_key)
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self.filter_combo)
        filter_row.addStretch()

        self.count_label = QLabel("")
        filter_row.addWidget(self.count_label)
        layout.addLayout(filter_row)

        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        # 底部按钮
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("清空全部记忆")
        clear_btn.setStyleSheet("color: #c0392b;")
        clear_btn.clicked.connect(self._clear_all)
        export_btn = QPushButton("导出…")
        export_btn.clicked.connect(self._export)
        import_btn = QPushButton("导入…")
        import_btn.clicked.connect(self._import)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(import_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        filter_type = self.filter_combo.currentData()
        if filter_type:
            items = self.memory.get_by_type(filter_type)
        else:
            items = self.memory.get_enabled()

        self.count_label.setText("共 %d 条" % len(items))

        if not items:
            empty = QLabel("还没有任何长期记忆～多和 Maid 聊聊吧！")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #999; padding: 40px;")
            self.vbox.addWidget(empty)
            return

        for m in reversed(items):
            row = self._build_row(m)
            self.vbox.addWidget(row)

    def _build_row(self, m):
        row = QFrame()
        row.setStyleSheet(
            "QFrame { border-bottom: 1px solid #f0f0f0; }"
        )
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(8, 8, 8, 8)
        row_layout.setSpacing(4)

        # 第一行：类型标签 + 时间
        header = QHBoxLayout()
        mem_type = m.get("type", "profile")
        type_label = QLabel(_TYPE_LABELS.get(mem_type, mem_type))
        color = _TYPE_COLORS.get(mem_type, "#666")
        type_label.setStyleSheet(
            "QLabel {"
            "  background: %s; color: white; border: none;"
            "  border-radius: 8px; padding: 2px 8px; font-size: 11px;"
            "}" % color
        )
        type_label.setFixedHeight(20)
        header.addWidget(type_label)

        importance = m.get("importance", 0.5)
        if importance >= 0.7:
            imp_text = "重要"
        elif importance >= 0.4:
            imp_text = "一般"
        else:
            imp_text = "次要"
        imp_label = QLabel(imp_text)
        imp_label.setStyleSheet("border: none; color: #999; font-size: 11px;")
        header.addWidget(imp_label)

        header.addStretch()

        time_str = m.get("created_at", "")[:16]
        time_label = QLabel(time_str)
        time_label.setStyleSheet("border: none; color: #aaa; font-size: 11px;")
        header.addWidget(time_label)

        row_layout.addLayout(header)

        # 第二行：记忆内容
        content_label = QLabel(m.get("content", ""))
        content_label.setWordWrap(True)
        content_label.setStyleSheet("border: none; font-size: 13px; padding: 2px 0;")
        content_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_layout.addWidget(content_label)

        # 第三行：标签 + 删除按钮
        footer = QHBoxLayout()
        tags = m.get("tags", [])
        if tags:
            tags_text = " ".join("#%s" % t for t in tags)
            tags_label = QLabel(tags_text)
            tags_label.setStyleSheet("border: none; color: #888; font-size: 11px;")
            footer.addWidget(tags_label)

        recall_count = m.get("recall_count", 0)
        if recall_count > 0:
            recall_label = QLabel("被想起 %d 次" % recall_count)
            recall_label.setStyleSheet("border: none; color: #aaa; font-size: 11px;")
            footer.addWidget(recall_label)

        footer.addStretch()

        del_btn = QPushButton("删除")
        del_btn.setFixedWidth(56)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(
            "QPushButton { border: none; color: #c0392b; font-size: 12px; }"
            "QPushButton:hover { color: #e74c3c; }"
        )
        del_btn.clicked.connect(
            lambda _=False, mid=m.get("id"): self._delete(mid)
        )
        footer.addWidget(del_btn)

        row_layout.addLayout(footer)
        return row

    def _delete(self, memory_id):
        if self.memory.delete(memory_id):
            self.refresh()

    def _export(self):
        """导出记忆为 JSON 文件。"""
        from datetime import datetime
        default_name = "maid-memories-%s.json" % datetime.now().strftime("%Y%m%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出长期记忆", default_name,
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        success = self.memory.export_to(path)
        if success:
            QMessageBox.information(self, "导出成功", "已导出 %d 条记忆到：\n%s" % (
                self.memory.enabled_count, path
            ))
        else:
            QMessageBox.warning(self, "导出失败", "写入文件时出错，请检查路径权限。")

    def _import(self):
        """从 JSON 文件导入记忆（合并，不覆盖）。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入长期记忆", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        count = self.memory.import_from(path)
        if count >= 0:
            QMessageBox.information(self, "导入成功", "已导入 %d 条新记忆。" % count)
            self.refresh()
        else:
            QMessageBox.warning(self, "导入失败", "文件格式不正确或无法读取。")

    def _clear_all(self):
        ret = QMessageBox.question(
            self, "确认",
            "确定要清空全部长期记忆吗？Maid 将彻底忘记对你的所有认知。\n此操作不可恢复。"
        )
        if ret == QMessageBox.Yes:
            self.memory.clear()
            self.refresh()
