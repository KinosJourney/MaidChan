# -*- coding: utf-8 -*-
"""番茄钟设置与控制面板。

倒计时实时显示由 MaidPet 上的浮动标签负责，
本窗口只提供时长选择、开始/取消、当日计数查看。
"""

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...config.constants import (
    DEFAULT_POMODORO_MINUTES,
    POMODORO_MAX_MINUTES,
    POMODORO_MIN_MINUTES,
    POMODORO_PRESETS,
)

_BTN_STYLE_ACTIVE = (
    "QPushButton {"
    "  background: #ffb7c5; color: white; border: none;"
    "  border-radius: 14px; padding: 8px 24px; font-size: 15px;"
    "  font-weight: bold;"
    "}"
    "QPushButton:hover { background: #ff9db0; }"
)
_BTN_STYLE_CANCEL = (
    "QPushButton {"
    "  background: #ccc; color: white; border: none;"
    "  border-radius: 14px; padding: 8px 24px; font-size: 15px;"
    "  font-weight: bold;"
    "}"
    "QPushButton:hover { background: #bbb; }"
)


class PomodoroDialog(QDialog):
    """番茄钟控制面板。

    Parameters
    ----------
    stats : PomodoroStats
        每日完成计数持久化对象。
    on_complete : callable(count)
        番茄完成时的回调。
    on_tick : callable(text) | None
        每次 tick 时回调，传入 ``"MM:SS"`` 格式文本，供外部显示倒计时。
    on_state_change : callable(running: bool) | None
        开始/取消/完成时回调，通知外部显示或隐藏倒计时。
    parent : QWidget | None
    """

    def __init__(self, stats, on_complete=None, on_tick=None,
                 on_state_change=None, parent=None):
        super().__init__(parent)
        self._stats = stats
        self._on_complete = on_complete
        self._on_tick = on_tick
        self._on_state_change = on_state_change

        self._end_time = 0.0
        self._running = False
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(200)
        self._tick_timer.timeout.connect(self._tick)

        self.setWindowTitle("番茄钟")
        self.setFixedSize(280, 220)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.CustomizeWindowHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        self._build_ui()
        self._update_count_label()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 16, 20, 16)

        # 时长设置
        dur_row = QHBoxLayout()
        dur_label = QLabel("专注时长(分钟)：")
        dur_label.setStyleSheet("font-size: 13px;")
        self._spin = QSpinBox()
        self._spin.setRange(POMODORO_MIN_MINUTES, POMODORO_MAX_MINUTES)
        self._spin.setValue(DEFAULT_POMODORO_MINUTES)
        self._spin.setSuffix(" min")
        self._spin.setStyleSheet("font-size: 13px; padding: 2px 4px;")
        dur_row.addWidget(dur_label)
        dur_row.addWidget(self._spin, 1)
        root.addLayout(dur_row)

        # 预设按钮
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for minutes in POMODORO_PRESETS:
            btn = QPushButton("%d分钟" % minutes)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton {"
                "  background: #fff0f3; border: 1px solid #ffb7c5;"
                "  border-radius: 10px; padding: 4px 10px; font-size: 12px;"
                "}"
                "QPushButton:hover { background: #ffe0e6; }"
                "QPushButton:disabled { background: #f5f5f5; color: #bbb; }"
            )
            btn.clicked.connect(lambda _, m=minutes: self._set_preset(m))
            preset_row.addWidget(btn)
        root.addLayout(preset_row)
        self._preset_row = preset_row

        # 状态提示（运行时显示剩余时间）
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("font-size: 13px; color: #e85d75;")
        root.addWidget(self._status_label)

        # 开始/取消按钮
        self._start_btn = QPushButton("开始专注")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setStyleSheet(_BTN_STYLE_ACTIVE)
        self._start_btn.clicked.connect(self._toggle)
        root.addWidget(self._start_btn, 0, Qt.AlignCenter)

        # 今日计数
        self._count_label = QLabel()
        self._count_label.setAlignment(Qt.AlignCenter)
        self._count_label.setStyleSheet("font-size: 13px; color: #8a6a73;")
        root.addWidget(self._count_label)

    # ---- 操作 ----

    def _set_preset(self, minutes):
        if not self._running:
            self._spin.setValue(minutes)

    def _toggle(self):
        if self._running:
            self._cancel()
        else:
            self._start()

    def _start(self):
        minutes = self._spin.value()
        self._end_time = time.monotonic() + minutes * 60
        self._running = True
        self._spin.setEnabled(False)
        self._set_presets_enabled(False)
        self._start_btn.setText("取消专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_CANCEL)
        self._tick_timer.start()
        self._tick()
        if self._on_state_change:
            self._on_state_change(True)

    def _cancel(self):
        self._tick_timer.stop()
        self._running = False
        self._spin.setEnabled(True)
        self._set_presets_enabled(True)
        self._start_btn.setText("开始专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_ACTIVE)
        self._status_label.setText("")
        if self._on_state_change:
            self._on_state_change(False)

    def _complete(self):
        self._tick_timer.stop()
        self._running = False
        self._spin.setEnabled(True)
        self._set_presets_enabled(True)
        self._start_btn.setText("开始专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_ACTIVE)
        self._status_label.setText("")
        count = self._stats.record_completion()
        self._update_count_label()
        if self._on_state_change:
            self._on_state_change(False)
        if self._on_complete:
            self._on_complete(count)

    def _tick(self):
        remaining = self._end_time - time.monotonic()
        if remaining <= 0:
            self._complete()
            return
        total_sec = int(remaining) + 1
        mm, ss = divmod(total_sec, 60)
        text = "%02d:%02d" % (mm, ss)
        self._status_label.setText("剩余 %s" % text)
        if self._on_tick:
            self._on_tick(text)

    # ---- 辅助 ----

    def _set_presets_enabled(self, enabled):
        for i in range(self._preset_row.count()):
            w = self._preset_row.itemAt(i).widget()
            if w:
                w.setEnabled(enabled)

    def _update_count_label(self):
        count = self._stats.today_count
        if count > 0:
            self._count_label.setText("今日已完成 %d 个番茄" % count)
        else:
            self._count_label.setText("今日还没有完成番茄哦，加油！")

    @property
    def is_running(self):
        return self._running

    def closeEvent(self, event):
        if self._running:
            event.ignore()
            self.hide()
        else:
            event.accept()

    def show_and_raise(self):
        self._update_count_label()
        self.show()
        self.raise_()
        self.activateWindow()
