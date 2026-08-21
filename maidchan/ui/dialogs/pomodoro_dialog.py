# -*- coding: utf-8 -*-
"""番茄钟设置与控制面板。

倒计时实时显示由 MaidPet 上的浮动标签负责，
本窗口只提供时长选择、开始/取消、当日计数查看。
"""

import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...core.sound import ChimePlayer
from ...config.constants import (
    DEFAULT_POMODORO_MINUTES,
    DEFAULT_REST_MINUTES,
    POMODORO_MAX_MINUTES,
    POMODORO_MIN_MINUTES,
    POMODORO_PRESETS,
    REST_MAX_MINUTES,
    REST_MIN_MINUTES,
    REST_PRESETS,
    WORK_METHODS,
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
    on_rest_done : callable() | None
        休息结束时回调，供外部显示提示气泡。
    parent : QWidget | None
    """

    _DEFAULT_HINT = "把鼠标放到上面的按钮，看看各工作法的介绍～"

    def __init__(self, stats, on_complete=None, on_tick=None,
                 on_state_change=None, on_rest_done=None, parent=None):
        super().__init__(parent)
        self._stats = stats
        self._on_complete = on_complete
        self._on_tick = on_tick
        self._on_state_change = on_state_change
        self._on_rest_done = on_rest_done

        self._end_time = 0.0
        self._paused_remaining = 0.0
        self._running = False
        self._paused = False
        self._is_resting = False
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(200)
        self._tick_timer.timeout.connect(self._tick)

        self._chime = ChimePlayer(self)

        self.setWindowTitle("番茄钟")
        self.setFixedSize(300, 420)
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

        # 科学工作法快速配置
        method_label = QLabel("工作法：")
        method_label.setStyleSheet("font-size: 13px;")
        root.addWidget(method_label)

        method_row = QHBoxLayout()
        method_row.setSpacing(6)
        self._method_tips = {}
        for name, focus, rest, tip in WORK_METHODS:
            btn = QPushButton(name)
            btn.setCursor(Qt.PointingHandCursor)
            hint = "%s（专注 %d 分钟 / 休息 %d 分钟）" % (tip, focus, rest)
            btn.setToolTip(hint)
            self._method_tips[btn] = hint
            btn.installEventFilter(self)
            btn.setStyleSheet(
                "QPushButton {"
                "  background: #ffb7c5; color: white; border: none;"
                "  border-radius: 10px; padding: 5px 6px; font-size: 12px;"
                "  font-weight: bold;"
                "}"
                "QPushButton:hover { background: #ff9db0; }"
                "QPushButton:disabled { background: #f0d6dc; color: #fff; }"
            )
            btn.clicked.connect(
                lambda _, f=focus, r=rest: self._apply_method(f, r)
            )
            method_row.addWidget(btn)
        root.addLayout(method_row)
        self._method_row = method_row

        # 工作法简介（鼠标划过上方按钮时显示）
        self._method_hint = QLabel(self._DEFAULT_HINT)
        self._method_hint.setWordWrap(True)
        self._method_hint.setAlignment(Qt.AlignCenter)
        self._method_hint.setMinimumHeight(34)
        self._method_hint.setStyleSheet(
            "QLabel {"
            "  background: #fff5f8; border: 1px solid #ffd6df;"
            "  border-radius: 8px; padding: 4px 8px;"
            "  font-size: 11px; color: #8a6a73;"
            "}"
        )
        root.addWidget(self._method_hint)

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

        # 休息时长设置
        rest_row = QHBoxLayout()
        rest_label = QLabel("休息时长(分钟)：")
        rest_label.setStyleSheet("font-size: 13px;")
        self._rest_spin = QSpinBox()
        self._rest_spin.setRange(REST_MIN_MINUTES, REST_MAX_MINUTES)
        self._rest_spin.setValue(DEFAULT_REST_MINUTES)
        self._rest_spin.setSuffix(" min")
        self._rest_spin.setStyleSheet("font-size: 13px; padding: 2px 4px;")
        rest_row.addWidget(rest_label)
        rest_row.addWidget(self._rest_spin, 1)
        root.addLayout(rest_row)

        # 休息预设按钮
        rest_preset_row = QHBoxLayout()
        rest_preset_row.setSpacing(6)
        for minutes in REST_PRESETS:
            btn = QPushButton("%d分钟" % minutes)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton {"
                "  background: #eef7ff; border: 1px solid #a9d3ff;"
                "  border-radius: 10px; padding: 4px 10px; font-size: 12px;"
                "}"
                "QPushButton:hover { background: #dcefff; }"
                "QPushButton:disabled { background: #f5f5f5; color: #bbb; }"
            )
            btn.clicked.connect(lambda _, m=minutes: self._set_rest_preset(m))
            rest_preset_row.addWidget(btn)
        root.addLayout(rest_preset_row)
        self._rest_preset_row = rest_preset_row

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

    def eventFilter(self, obj, event):
        tip = self._method_tips.get(obj)
        if tip is not None:
            if event.type() == QEvent.Enter:
                self._method_hint.setText(tip)
            elif event.type() == QEvent.Leave:
                self._method_hint.setText(self._DEFAULT_HINT)
        return super().eventFilter(obj, event)

    def _apply_method(self, focus_minutes, rest_minutes):
        if not self._running:
            self._spin.setValue(focus_minutes)
            self._rest_spin.setValue(rest_minutes)

    def _set_preset(self, minutes):
        if not self._running:
            self._spin.setValue(minutes)

    def _set_rest_preset(self, minutes):
        if not self._running:
            self._rest_spin.setValue(minutes)

    def _toggle(self):
        if self._running:
            self._cancel()
        else:
            self._start()

    def _start(self):
        minutes = self._spin.value()
        self._end_time = time.monotonic() + minutes * 60
        self._paused_remaining = 0.0
        self._running = True
        self._paused = False
        self._is_resting = False
        self._set_inputs_enabled(False)
        self._start_btn.setText("取消专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_CANCEL)
        self._tick_timer.start()
        self._tick()
        if self._on_state_change:
            self._on_state_change(True)
        self.hide()

    def _cancel(self):
        self._tick_timer.stop()
        resting = self._is_resting
        self._running = False
        self._paused = False
        self._paused_remaining = 0.0
        self._is_resting = False
        self._set_inputs_enabled(True)
        self._start_btn.setText("开始专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_ACTIVE)
        self._status_label.setText("")
        if self._on_state_change:
            self._on_state_change(False)
        if resting and self._on_rest_done:
            self._on_rest_done()

    def _complete(self):
        self._tick_timer.stop()
        self._running = False
        self._paused = False
        self._paused_remaining = 0.0
        self._is_resting = False
        self._set_inputs_enabled(True)
        self._start_btn.setText("开始专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_ACTIVE)
        self._status_label.setText("")
        count = self._stats.record_completion()
        self._update_count_label()
        self._play_sound()
        if self._on_state_change:
            self._on_state_change(False)
        if self._on_complete:
            self._on_complete(count)
        self._prompt_rest()

    def _prompt_rest(self):
        rest_minutes = self._rest_spin.value()
        dlg = _RestPromptDialog(rest_minutes, parent=self)
        result = dlg.exec()
        if result == QDialog.Accepted:
            self._start_rest()
        elif result == _RestPromptDialog.SKIP_REST:
            self._start()

    def _start_rest(self):
        minutes = self._rest_spin.value()
        self._end_time = time.monotonic() + minutes * 60
        self._paused_remaining = 0.0
        self._running = True
        self._paused = False
        self._is_resting = True
        self._set_inputs_enabled(False)
        self._start_btn.setText("跳过休息")
        self._start_btn.setStyleSheet(_BTN_STYLE_CANCEL)
        self._tick_timer.start()
        self._tick()
        if self._on_state_change:
            self._on_state_change(True)

    def _rest_complete(self):
        self._tick_timer.stop()
        self._running = False
        self._paused = False
        self._paused_remaining = 0.0
        self._is_resting = False
        self._set_inputs_enabled(True)
        self._start_btn.setText("开始专注")
        self._start_btn.setStyleSheet(_BTN_STYLE_ACTIVE)
        self._status_label.setText("")
        self._play_sound()
        if self._on_state_change:
            self._on_state_change(False)
        if self._on_rest_done:
            self._on_rest_done()
        # 休息结束后循环开始下一个番茄
        self._start()

    def _tick(self):
        remaining = self._end_time - time.monotonic()
        if remaining <= 0:
            if self._is_resting:
                self._rest_complete()
            else:
                self._complete()
            return
        total_sec = int(remaining) + 1
        mm, ss = divmod(total_sec, 60)
        text = "%02d:%02d" % (mm, ss)
        prefix = "休息中" if self._is_resting else "剩余"
        self._status_label.setText("%s %s" % (prefix, text))
        if self._on_tick:
            self._on_tick(text)

    def toggle_pause(self):
        """暂停或继续当前专注倒计时；休息倒计时不支持暂停。"""
        if not self._running or self._is_resting:
            return
        if self._paused:
            self._end_time = time.monotonic() + self._paused_remaining
            self._paused = False
            self._tick_timer.start()
            self._tick()
            return

        self._paused_remaining = max(0.0, self._end_time - time.monotonic())
        self._paused = True
        self._tick_timer.stop()
        total_sec = max(1, int(self._paused_remaining) + 1)
        mm, ss = divmod(total_sec, 60)
        self._status_label.setText("已暂停 %02d:%02d" % (mm, ss))

    def skip_rest(self):
        """跳过当前休息倒计时，并立即开始下一轮专注。"""
        if self._running and self._is_resting:
            self._cancel()
            self._start()

    # ---- 音效 ----

    def _play_sound(self):
        self._chime.play()

    # ---- 辅助 ----

    def _set_inputs_enabled(self, enabled):
        self._spin.setEnabled(enabled)
        self._rest_spin.setEnabled(enabled)
        self._set_presets_enabled(enabled)

    def _set_presets_enabled(self, enabled):
        for row in (self._method_row, self._preset_row, self._rest_preset_row):
            for i in range(row.count()):
                w = row.itemAt(i).widget()
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

    @property
    def is_resting(self):
        return self._is_resting

    @property
    def is_paused(self):
        return self._paused

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


class _RestPromptDialog(QDialog):
    """番茄完成后询问是否休息的粉色风格弹窗。"""

    SKIP_REST = 2

    def __init__(self, rest_minutes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("番茄钟")
        self.setFixedSize(420, 190)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._build_ui(rest_minutes)

    def _build_ui(self, rest_minutes):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QLabel(self)
        card.setStyleSheet(
            "QLabel {"
            "  background: #fff5f8; border: 2px solid #ffb7c5;"
            "  border-radius: 18px;"
            "}"
        )
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(24, 22, 24, 20)
        body.setSpacing(16)

        title = QLabel("番茄完成啦！")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #e85d75;"
            " background: transparent; border: none;"
        )
        body.addWidget(title)

        msg = QLabel("要进入 %d 分钟休息吗？" % rest_minutes)
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet(
            "font-size: 14px; color: #8a6a73;"
            " background: transparent; border: none;"
        )
        body.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        exit_btn = QPushButton("退出番茄钟模式")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(
            "QPushButton {"
            "  background: #f0e6ea; color: #8a6a73; border: none;"
            "  border-radius: 14px; padding: 8px 12px; font-size: 13px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover { background: #e6d8de; }"
        )
        exit_btn.clicked.connect(self.reject)

        skip_btn = QPushButton("跳过休息")
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.setStyleSheet(
            "QPushButton {"
            "  background: #fff0f3; color: #e85d75;"
            "  border: 1px solid #ffb7c5;"
            "  border-radius: 14px; padding: 8px 12px; font-size: 13px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover { background: #ffe0e6; }"
        )
        skip_btn.clicked.connect(lambda: self.done(self.SKIP_REST))

        rest_btn = QPushButton("开始休息")
        rest_btn.setCursor(Qt.PointingHandCursor)
        rest_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ffb7c5; color: white; border: none;"
            "  border-radius: 14px; padding: 8px 12px; font-size: 13px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover { background: #ff9db0; }"
        )
        rest_btn.clicked.connect(self.accept)
        rest_btn.setDefault(True)

        btn_row.addWidget(exit_btn, 1)
        btn_row.addWidget(skip_btn, 1)
        btn_row.addWidget(rest_btn, 1)
        body.addLayout(btn_row)
