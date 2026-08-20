# -*- coding: utf-8 -*-
"""待办提醒服务。

不为每条待办创建「几小时后触发」的超长 QTimer（这类定时器在系统休眠、
改系统时钟、或超出 Qt 定时器时长上限时并不可靠），而是通过统一 ``Scheduler``
每隔固定间隔扫描一次待办列表，按当前时间决定要不要提醒：

- 到点前 ``advance_minutes`` 分钟：发一次「提前提醒」。
- 到点：发一次「到点提醒」。
- 若应用休眠 / 关闭期间错过了提醒，恢复后只补发一次「错过提醒」。

发提醒前先把标记写回存储，再触发通知，保证同一阶段最多提醒一次，重启也不重复。
"""

from datetime import datetime, timedelta

from ..config.constants import (
    REMINDER_ADVANCE_MINUTES,
    REMINDER_MISSED_THRESHOLD_SECONDS,
    REMINDER_PRIORITY,
    REMINDER_SCAN_INTERVAL_SECONDS,
)
from ..storage.todo import STATUS_PENDING, parse_dt

_SCAN_TASK_ID = "reminder.scan"
_GROUP = "reminders"


class ReminderService:
    """周期扫描待办并发出提醒。

    Parameters
    ----------
    store : TodoStore
        待办存储。
    scheduler : Scheduler
        统一调度器（需支持 ``schedule_repeating`` / ``cancel``）。
    notify : callable(text, priority)
        发送提醒气泡的回调。
    play_sound : callable() | None
        触发提示音的回调（可选）。
    name_getter : callable() -> str | None
        获取对主人的称呼，用于个性化文案（可选）。
    now_fn : callable() -> datetime
        返回「当前时间」，便于测试注入可控时钟。
    advance_minutes / scan_interval_seconds / missed_threshold_seconds / priority
        行为参数，默认取自 constants。
    """

    def __init__(self, store, scheduler, notify, play_sound=None,
                 name_getter=None, now_fn=None,
                 advance_minutes=REMINDER_ADVANCE_MINUTES,
                 scan_interval_seconds=REMINDER_SCAN_INTERVAL_SECONDS,
                 missed_threshold_seconds=REMINDER_MISSED_THRESHOLD_SECONDS,
                 priority=REMINDER_PRIORITY):
        self._store = store
        self._scheduler = scheduler
        self._notify = notify
        self._play_sound = play_sound
        self._name_getter = name_getter
        self._now_fn = now_fn or datetime.now
        self._advance = advance_minutes
        self._scan_interval_ms = int(scan_interval_seconds * 1000)
        self._missed_threshold = missed_threshold_seconds
        self._priority = priority

    # ---- 生命周期 ----
    def start(self):
        """启动周期扫描，并立即扫描一次（处理启动时已到点 / 已错过的待办）。"""
        self._scheduler.schedule_repeating(
            _SCAN_TASK_ID, self._scan_interval_ms, self._scan, group=_GROUP,
        )
        self.refresh()

    def stop(self):
        self._scheduler.cancel(_SCAN_TASK_ID)

    def refresh(self):
        """立即扫描一次。待办增删改后调用，让新的时间尽快生效。"""
        self._scan()

    # ---- 扫描 ----
    def _scan(self):
        now = self._now_fn()
        for todo in list(self._store.pending()):
            if todo.get("status") != STATUS_PENDING:
                continue
            due = parse_dt(todo.get("due_at"))
            if due is None:
                continue
            self._evaluate(todo, due, now)

    def _evaluate(self, todo, due, now):
        pre_time = due - timedelta(minutes=self._advance)
        todo_id = todo.get("id")

        if now >= due:
            if todo.get("due_reminded_at"):
                return
            # 先写标记再通知，避免通知过程中再次扫描导致重复。
            self._store.mark_due_reminded(todo_id, now=now)
            missed = (now - due).total_seconds() > self._missed_threshold
            self._emit(self._due_text(todo, due, missed))
        elif now >= pre_time:
            if todo.get("pre_reminded_at"):
                return
            self._store.mark_pre_reminded(todo_id, now=now)
            self._emit(self._pre_text(todo, due))

    def _emit(self, text):
        self._notify(text, self._priority)
        if self._play_sound is not None:
            self._play_sound()

    # ---- 文案 ----
    def _name(self):
        if self._name_getter is None:
            return "主人"
        return self._name_getter() or "主人"

    def _pre_text(self, todo, due):
        return "%s，还有 %d 分钟就到「%s」啦，做好准备哦～" % (
            self._name(), self._advance, todo.get("content", ""),
        )

    def _due_text(self, todo, due, missed):
        content = todo.get("content", "")
        if missed:
            return "%s，刚才错过了一个提醒：「%s」（原定 %s）。" % (
                self._name(), content, due.strftime("%m-%d %H:%M"),
            )
        return "%s，时间到啦！记得「%s」哦～" % (self._name(), content)
