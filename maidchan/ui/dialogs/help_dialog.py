# -*- coding: utf-8 -*-
"""帮助 / 说明（动态渲染 readme.md）。"""

import os
import sys

from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QMessageBox,
)

from ...config.paths import app_base_dir, resource_dir


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助 / 说明")
        self.resize(600, 640)
        layout = QVBoxLayout(self)

        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        layout.addWidget(self.viewer, 1)

        btn_row = QHBoxLayout()
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self.reload_md)
        open_btn = QPushButton("用系统编辑器打开")
        open_btn.clicked.connect(self._open_external)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(reload_btn)
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.reload_md()

    def _readme_path(self):
        # 打包版优先读应用旁的外部文件，方便手动修改
        candidates = [
            os.path.join(app_base_dir(), "readme.md"),
            os.path.join(resource_dir(), "readme.md"),
            os.path.join(app_base_dir(), "README.md"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return candidates[0]

    def reload_md(self):
        path = self._readme_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    md = f.read()
                self.viewer.setMarkdown(md)
                return
            except Exception:
                pass
        self.viewer.setMarkdown(
            "# 未找到 readme.md\n\n请在程序目录下创建 `readme.md` 文件。"
        )

    def _open_external(self):
        path = self._readme_path()
        try:
            if sys.platform == "darwin":
                os.system('open "%s"' % path)
            elif sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore
            else:
                os.system('xdg-open "%s"' % path)
        except Exception:
            QMessageBox.information(self, "提示", "无法打开：%s" % path)
