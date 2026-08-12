# -*- coding: utf-8 -*-
"""统一定时任务调度器。

把原本散落在 ``MaidPet`` / ``SpeechBubble`` 里的多个 ``QTimer`` 收敛到一处：
每个任务用唯一的 ``task_id`` 标识，可选归入某个 ``group``，便于将来「勿扰模式」
一次性取消一整组任务，也避免忘记 ``stop()`` 造成的定时器泄漏。

内部仍使用 ``QTimer``，因此必须在 Qt 事件循环中使用。
"""

from PySide6.QtCore import QObject, QTimer


class Scheduler(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timers = {}          # task_id -> QTimer
        self._groups = {}          # task_id -> group name

    # ---- 注册 ----
    def schedule_once(self, task_id, delay_ms, callback, group=None):
        """在 delay_ms 毫秒后执行一次 callback。同名任务会被替换。"""
        self.cancel(task_id)
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _fire():
            # 先注销再回调：这样回调里可以用同一 task_id 重新排程。
            self._forget(task_id)
            callback()

        timer.timeout.connect(_fire)
        self._register(task_id, timer, group)
        timer.start(int(delay_ms))

    def schedule_repeating(self, task_id, interval_ms, callback, group=None):
        """每隔 interval_ms 毫秒重复执行 callback。同名任务会被替换。"""
        self.cancel(task_id)
        timer = QTimer(self)
        timer.setSingleShot(False)
        timer.timeout.connect(callback)
        self._register(task_id, timer, group)
        timer.start(int(interval_ms))

    # ---- 取消 ----
    def cancel(self, task_id):
        timer = self._timers.get(task_id)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._forget(task_id)

    def cancel_all(self, group=None):
        for task_id in list(self._timers.keys()):
            if group is None or self._groups.get(task_id) == group:
                self.cancel(task_id)

    def shutdown(self):
        """退出时调用：停止并清理全部任务。"""
        self.cancel_all()

    # ---- 查询 ----
    def is_active(self, task_id):
        timer = self._timers.get(task_id)
        return bool(timer is not None and timer.isActive())

    # ---- 内部 ----
    def _register(self, task_id, timer, group):
        self._timers[task_id] = timer
        if group is not None:
            self._groups[task_id] = group

    def _forget(self, task_id):
        self._timers.pop(task_id, None)
        self._groups.pop(task_id, None)
