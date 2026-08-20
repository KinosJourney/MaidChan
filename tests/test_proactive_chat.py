# -*- coding: utf-8 -*-
"""主动陪聊服务测试。

用 Stub Scheduler + 可控时钟 + 注入回调做确定性测试，不依赖 Qt / 网络，
覆盖：番茄钟 / 免打扰 / 空闲不足 / 正忙 / 启动缓冲 / 间隔 / 每日上限 /
类别轮换 / 跨午夜每日重置 / 无内容时请求刷新。
"""

import unittest
from datetime import datetime, timedelta

from maidchan.core.proactive_chat_service import ProactiveChatService, _in_quiet_hours


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


class Harness:
    def __init__(self, **overrides):
        self.settings = {
            "proactive_chat_enabled": True,
            "proactive_chat_categories": ["news"],
            "proactive_chat_interval_minutes": 45,
            "proactive_chat_min_idle_minutes": 10,
            "proactive_chat_daily_limit": 8,
            "proactive_chat_quiet_start": 23,
            "proactive_chat_quiet_end": 8,
        }
        self.settings.update(overrides)
        self.sched = StubScheduler()
        self.clock = Clock(datetime(2026, 8, 20, 14, 0, 0))
        self.idle = 1200.0            # 20 分钟空闲
        self.pomodoro = False
        self.blocked = False
        self.trigger_result = True
        self.triggered = []           # (category, item)
        self.refresh_calls = [0]
        self.available = {"news", "gossip", "philosophy", "trivia"}

        self.svc = ProactiveChatService(
            scheduler=self.sched,
            trigger=self._trigger,
            pick_item=self._pick,
            request_refresh=self._refresh,
            is_blocked=lambda: self.blocked,
            is_pomodoro_running=lambda: self.pomodoro,
            idle_seconds=lambda: self.idle,
            settings_getter=self.settings.get,
            now_fn=self.clock,
        )
        self.svc.start()
        # 越过启动缓冲期
        self.clock.advance(minutes=6)

    def _trigger(self, category, item):
        if self.trigger_result:
            self.triggered.append((category, item))
        return self.trigger_result

    def _pick(self, category):
        if category in self.available:
            return {"uid": "%s-1" % category, "title": category, "source": "s"}
        return None

    def _refresh(self):
        self.refresh_calls[0] += 1

    def tick(self):
        self.svc._maybe_chat()


class ProactiveChatServiceTest(unittest.TestCase):
    def test_start_registers_tasks(self):
        h = Harness()
        self.assertIn("proactive.check", h.sched.tasks)
        self.assertIn("proactive.refresh", h.sched.tasks)
        self.assertGreaterEqual(h.refresh_calls[0], 1)  # start 立即刷新一次

    def test_happy_path_triggers(self):
        h = Harness()
        h.tick()
        self.assertEqual(len(h.triggered), 1)
        self.assertEqual(h.triggered[0][0], "news")

    def test_disabled_no_trigger(self):
        h = Harness(proactive_chat_enabled=False)
        h.tick()
        self.assertEqual(h.triggered, [])

    def test_pomodoro_blocks(self):
        h = Harness()
        h.pomodoro = True
        h.tick()
        self.assertEqual(h.triggered, [])

    def test_busy_blocks(self):
        h = Harness()
        h.blocked = True
        h.tick()
        self.assertEqual(h.triggered, [])

    def test_idle_insufficient(self):
        h = Harness()
        h.idle = 60.0  # 只空闲 1 分钟 < 10 分钟
        h.tick()
        self.assertEqual(h.triggered, [])

    def test_startup_grace(self):
        h = Harness()
        # 回到缓冲期内（start 后不到 5 分钟）
        h.clock.now = h.svc._started_at + timedelta(minutes=2)
        h.tick()
        self.assertEqual(h.triggered, [])

    def test_quiet_hours(self):
        h = Harness()
        h.clock.now = datetime(2026, 8, 20, 23, 30, 0)  # 免打扰时段内
        h.tick()
        self.assertEqual(h.triggered, [])

    def test_interval_gate(self):
        h = Harness()
        h.tick()
        self.assertEqual(len(h.triggered), 1)
        # 距上次不足 45 分钟：不触发
        h.clock.advance(minutes=10)
        h.tick()
        self.assertEqual(len(h.triggered), 1)
        # 超过间隔：再次触发
        h.clock.advance(minutes=40)
        h.tick()
        self.assertEqual(len(h.triggered), 2)

    def test_daily_limit(self):
        h = Harness(proactive_chat_daily_limit=2)
        for _ in range(5):
            h.tick()
            h.clock.advance(minutes=50)
        self.assertEqual(len(h.triggered), 2)

    def test_daily_reset_next_day(self):
        h = Harness(proactive_chat_daily_limit=1)
        h.tick()
        self.assertEqual(len(h.triggered), 1)
        h.clock.advance(minutes=50)
        h.tick()  # 当日已达上限
        self.assertEqual(len(h.triggered), 1)
        # 次日同一时段，计数重置
        h.clock.advance(days=1)
        h.tick()
        self.assertEqual(len(h.triggered), 2)

    def test_category_rotation_avoids_repeat(self):
        h = Harness(proactive_chat_categories=["news", "trivia"],
                    proactive_chat_daily_limit=20)
        cats = []
        for _ in range(6):
            h.tick()
            h.clock.advance(minutes=50)
        cats = [c for c, _ in h.triggered]
        self.assertEqual(len(cats), 6)
        for prev, cur in zip(cats, cats[1:]):
            self.assertNotEqual(prev, cur)  # 连续两次不同类

    def test_no_content_requests_refresh(self):
        h = Harness(proactive_chat_categories=["news"])
        h.available = set()  # 没有任何内容
        before = h.refresh_calls[0]
        h.tick()
        self.assertEqual(h.triggered, [])
        self.assertGreater(h.refresh_calls[0], before)

    def test_falls_back_to_other_category_with_content(self):
        h = Harness(proactive_chat_categories=["news", "philosophy"])
        h.available = {"philosophy"}  # 只有哲学有内容
        h.tick()
        self.assertEqual(len(h.triggered), 1)
        self.assertEqual(h.triggered[0][0], "philosophy")

    def test_trigger_failure_not_counted(self):
        h = Harness()
        h.trigger_result = False
        h.tick()
        self.assertEqual(h.triggered, [])
        # 未计入 last_fired，恢复后可立即触发
        h.trigger_result = True
        h.tick()
        self.assertEqual(len(h.triggered), 1)


class QuietHoursTest(unittest.TestCase):
    def test_same_start_end_disabled(self):
        self.assertFalse(_in_quiet_hours(3, 0, 0))

    def test_normal_range(self):
        self.assertTrue(_in_quiet_hours(13, 12, 14))
        self.assertFalse(_in_quiet_hours(15, 12, 14))

    def test_cross_midnight(self):
        self.assertTrue(_in_quiet_hours(23, 23, 8))
        self.assertTrue(_in_quiet_hours(3, 23, 8))
        self.assertFalse(_in_quiet_hours(9, 23, 8))


if __name__ == "__main__":
    unittest.main()
