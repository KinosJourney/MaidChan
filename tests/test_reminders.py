# -*- coding: utf-8 -*-
"""待办提醒服务测试。

用可控时钟 + Stub Scheduler / Notifier 做确定性测试，不依赖 Qt 事件循环，
覆盖：提前 2 分钟、到点、创建时不足 2 分钟、错过补发、重启防重复、
完成 / 删除后不再提醒。
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from maidchan.core.reminder_service import ReminderService
from maidchan.storage.todo import TodoStore

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class StubScheduler:
    def __init__(self):
        self.tasks = {}

    def schedule_repeating(self, task_id, interval_ms, callback, group=None):
        self.tasks[task_id] = callback

    def cancel(self, task_id):
        self.tasks.pop(task_id, None)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now = self.now + timedelta(**kwargs)


class ReminderServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=REPO_ROOT)
        self.store = TodoStore(os.path.join(self.tmp, "todos.json"), advance_minutes=2)
        self.sched = StubScheduler()
        self.notes = []      # (text, priority)
        self.sounds = [0]
        self.clock = Clock(datetime(2026, 8, 20, 10, 0, 0))
        self.svc = ReminderService(
            store=self.store,
            scheduler=self.sched,
            notify=lambda t, p: self.notes.append((t, p)),
            play_sound=lambda: self.sounds.__setitem__(0, self.sounds[0] + 1),
            name_getter=lambda: "小明",
            now_fn=self.clock,
            advance_minutes=2,
            scan_interval_seconds=20,
            missed_threshold_seconds=90,
            priority=5,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scan(self):
        self.svc._scan()

    def test_start_registers_scan(self):
        self.svc.start()
        self.assertIn("reminder.scan", self.sched.tasks)

    def test_pre_then_due(self):
        due = self.clock.now + timedelta(minutes=10)
        item = self.store.add("开会", due, now=self.clock.now)

        # 还早：不提醒
        self._scan()
        self.assertEqual(self.notes, [])

        # 到提前 2 分钟窗口：发提前提醒
        self.clock.now = due - timedelta(minutes=1)
        self._scan()
        self.assertEqual(len(self.notes), 1)
        self.assertIn("还有 2 分钟", self.notes[0][0])
        self.assertEqual(self.notes[0][1], 5)
        self.assertEqual(self.sounds[0], 1)

        # 再次扫描不重复提前提醒
        self._scan()
        self.assertEqual(len(self.notes), 1)

        # 到点：发到点提醒
        self.clock.now = due
        self._scan()
        self.assertEqual(len(self.notes), 2)
        self.assertIn("时间到啦", self.notes[1][0])

        # 到点后再扫描不重复
        self.clock.now = due + timedelta(seconds=30)
        self._scan()
        self.assertEqual(len(self.notes), 2)
        self.assertIsNotNone(self.store.get(item["id"])["due_reminded_at"])

    def test_created_within_advance_only_due(self):
        # 距离截止 1 分钟 < 2 分钟：跳过提前提醒
        due = self.clock.now + timedelta(minutes=1)
        self.store.add("马上开会", due, now=self.clock.now)
        self._scan()
        self.assertEqual(self.notes, [])  # 还没到点
        self.clock.now = due
        self._scan()
        self.assertEqual(len(self.notes), 1)
        self.assertIn("时间到啦", self.notes[0][0])

    def test_missed_while_closed_single_reminder(self):
        # 待办在“过去”很久才被扫描到（模拟应用关闭/休眠期间错过）
        due = self.clock.now + timedelta(minutes=10)
        self.store.add("已经错过的事", due, now=self.clock.now)
        self.clock.now = due + timedelta(minutes=30)
        self._scan()
        self.assertEqual(len(self.notes), 1)
        self.assertIn("错过", self.notes[0][0])
        # 再扫描不重复
        self._scan()
        self.assertEqual(len(self.notes), 1)

    def test_restart_no_duplicate(self):
        due = self.clock.now + timedelta(minutes=10)
        self.store.add("开会", due, now=self.clock.now)
        self.clock.now = due + timedelta(seconds=10)
        self._scan()
        self.assertEqual(len(self.notes), 1)

        # 模拟重启：用同一份 JSON 新建 store 与 service
        store2 = TodoStore(self.store.path, advance_minutes=2)
        notes2 = []
        svc2 = ReminderService(
            store=store2,
            scheduler=StubScheduler(),
            notify=lambda t, p: notes2.append((t, p)),
            now_fn=self.clock,
            advance_minutes=2,
        )
        svc2.refresh()
        self.assertEqual(notes2, [])  # 标记已持久化，不再重复提醒

    def test_done_todo_not_reminded(self):
        due = self.clock.now + timedelta(minutes=1)
        item = self.store.add("交作业", due, now=self.clock.now)
        self.store.mark_done(item["id"], now=self.clock.now)
        self.clock.now = due + timedelta(minutes=5)
        self._scan()
        self.assertEqual(self.notes, [])

    def test_deleted_todo_not_reminded(self):
        due = self.clock.now + timedelta(minutes=1)
        item = self.store.add("买菜", due, now=self.clock.now)
        self.store.delete(item["id"])
        self.clock.now = due
        self._scan()
        self.assertEqual(self.notes, [])

    def test_no_play_sound_optional(self):
        svc = ReminderService(
            store=self.store,
            scheduler=StubScheduler(),
            notify=lambda t, p: self.notes.append((t, p)),
            now_fn=self.clock,
            advance_minutes=2,
        )
        due = self.clock.now + timedelta(minutes=1)
        self.store.add("测试无声", due, now=self.clock.now)
        self.clock.now = due
        svc._scan()  # 不应因缺少 play_sound 而报错
        self.assertEqual(len(self.notes), 1)


if __name__ == "__main__":
    unittest.main()
