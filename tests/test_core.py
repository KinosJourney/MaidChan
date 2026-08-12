# -*- coding: utf-8 -*-
"""核心层测试：状态机、通知优先级、调度器。

状态机与通知用桩对象做确定性测试；调度器用真实 Qt 事件循环做定时验证。
"""

import unittest

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from maidchan.core.character_state import Action
from maidchan.core.state_machine import CharacterStateMachine
from maidchan.core.notifications import NotificationManager
from maidchan.core.scheduler import Scheduler


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


class StubScheduler:
    """记录被排程的任务，可手动触发，用于确定性测试。"""

    def __init__(self):
        self.tasks = {}       # task_id -> callback
        self.repeating = set()

    def schedule_once(self, task_id, delay_ms, callback, group=None):
        self.tasks[task_id] = callback

    def schedule_repeating(self, task_id, interval_ms, callback, group=None):
        self.tasks[task_id] = callback
        self.repeating.add(task_id)

    def cancel(self, task_id):
        self.tasks.pop(task_id, None)
        self.repeating.discard(task_id)

    def cancel_all(self, group=None):
        self.tasks.clear()
        self.repeating.clear()

    def is_active(self, task_id):
        return task_id in self.tasks

    def fire(self, task_id):
        self.tasks[task_id]()


class StateMachineTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.renders = []
        self.mute = [False]
        self.sched = StubScheduler()
        self.sm = CharacterStateMachine(
            pixmaps={"origin": "ORIGIN", "open": "OPEN", "blink": "BLINK"},
            render=self.renders.append,
            scheduler=self.sched,
            mute_getter=lambda: self.mute[0],
        )

    def test_start_renders_origin_and_schedules_blink(self):
        self.sm.start()
        self.assertEqual(self.renders[-1], "ORIGIN")
        self.assertTrue(self.sched.is_active("state.blink"))

    def test_speaking_mouth_animation(self):
        self.sm.start()
        self.sm.begin_speaking()
        self.assertEqual(self.sm.action, Action.SPEAKING)
        self.assertTrue(self.sm.is_speaking)
        self.assertTrue(self.sched.is_active("state.mouth"))
        # 嘴巴逐帧：先张后合
        self.sched.fire("state.mouth")
        self.assertEqual(self.renders[-1], "OPEN")
        self.sched.fire("state.mouth")
        self.assertEqual(self.renders[-1], "ORIGIN")

    def test_end_sentence_closes_mouth(self):
        self.sm.start()
        self.sm.begin_speaking()
        self.sm.end_sentence()
        self.assertFalse(self.sched.is_active("state.mouth"))
        self.assertEqual(self.renders[-1], "ORIGIN")
        # 句间仍处于说话态
        self.assertTrue(self.sm.is_speaking)

    def test_end_speaking_returns_idle(self):
        self.sm.start()
        self.sm.begin_speaking()
        self.sm.end_speaking()
        self.assertEqual(self.sm.action, Action.IDLE)
        self.assertFalse(self.sched.is_active("state.mouth"))
        self.assertEqual(self.renders[-1], "ORIGIN")

    def test_mute_freezes_open_mouth(self):
        self.mute[0] = True
        self.sm.start()
        self.sm.begin_speaking()
        self.assertEqual(self.renders[-1], "OPEN")
        self.assertFalse(self.sched.is_active("state.mouth"))

    def test_blink_while_idle(self):
        self.sm.start()
        self.sched.fire("state.blink")
        self.assertEqual(self.renders[-1], "BLINK")
        # 眨眼后应重新排程下一次眨眼，并安排收尾
        self.assertTrue(self.sched.is_active("state.blink"))
        self.assertTrue(self.sched.is_active("state.blink_end"))
        self.sched.fire("state.blink_end")
        self.assertEqual(self.renders[-1], "ORIGIN")

    def test_no_blink_while_speaking(self):
        self.sm.start()
        self.sm.begin_speaking()
        before = list(self.renders)
        self.sched.fire("state.blink")
        # 说话时不眨眼：不应渲染 BLINK，也不安排收尾
        self.assertNotIn("BLINK", self.renders[len(before):])
        self.assertFalse(self.sched.is_active("state.blink_end"))
        # 但仍会安排下一次眨眼
        self.assertTrue(self.sched.is_active("state.blink"))


class StubBubble:
    def __init__(self):
        self._visible = False
        self.spoken = []
        self.on_sentence_typing = None
        self.on_sentence_done = None
        self.on_all_done = None
        self.on_geometry_changed = None

    def isVisible(self):
        return self._visible

    def speak(self, sentences):
        self._visible = True
        self.spoken.append(sentences)


class StubState:
    def __init__(self):
        self.calls = []

    def begin_speaking(self):
        self.calls.append("speak")

    def end_sentence(self):
        self.calls.append("sentence")

    def end_speaking(self):
        self.calls.append("done")


class NotificationTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.bubble = StubBubble()
        self.state = StubState()
        self.positions = []
        self.nm = NotificationManager(
            bubble=self.bubble,
            split_fn=lambda t: [t],
            position_cb=lambda: self.positions.append(1),
            state_machine=self.state,
        )

    def test_show_speaks_and_positions(self):
        self.nm.show("你好")
        self.assertEqual(self.bubble.spoken, [["你好"]])
        self.assertEqual(len(self.positions), 1)

    def test_high_priority_not_interrupted_by_low(self):
        self.nm.show("紧急", priority=5)
        self.nm.show("闲聊", priority=1)  # 应被忽略
        self.assertEqual(self.bubble.spoken, [["紧急"]])
        # 说完之后优先级复位，普通消息可再次显示
        self.bubble.on_all_done()
        self.nm.show("闲聊", priority=1)
        self.assertEqual(self.bubble.spoken, [["紧急"], ["闲聊"]])

    def test_default_priority_interrupts(self):
        # 默认优先级都为 0，与旧版一致：后一句会覆盖前一句
        self.nm.show("第一句")
        self.nm.show("第二句")
        self.assertEqual(self.bubble.spoken, [["第一句"], ["第二句"]])

    def test_bubble_callbacks_forward_to_state(self):
        self.bubble.on_sentence_typing()
        self.bubble.on_sentence_done()
        self.bubble.on_all_done()
        self.assertEqual(self.state.calls, ["speak", "sentence", "done"])


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.sched = Scheduler()

    def tearDown(self):
        self.sched.shutdown()

    def _spin(self, ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def test_schedule_once_fires_and_cleans_up(self):
        fired = []
        self.sched.schedule_once("t", 20, lambda: fired.append(1))
        self.assertTrue(self.sched.is_active("t"))
        self._spin(120)
        self.assertEqual(fired, [1])
        self.assertFalse(self.sched.is_active("t"))

    def test_cancel_prevents_fire(self):
        fired = []
        self.sched.schedule_once("c", 200, lambda: fired.append("bad"))
        self.assertTrue(self.sched.is_active("c"))
        self.sched.cancel("c")
        self.assertFalse(self.sched.is_active("c"))
        self._spin(120)
        self.assertEqual(fired, [])

    def test_repeating_and_cancel_all_group(self):
        cnt = [0]

        def tick():
            cnt[0] += 1

        self.sched.schedule_repeating("r", 20, tick, group="g")
        self._spin(150)
        self.assertGreaterEqual(cnt[0], 2)
        self.sched.cancel_all(group="g")
        self.assertFalse(self.sched.is_active("r"))
        stopped = cnt[0]
        self._spin(80)
        self.assertEqual(cnt[0], stopped)

    def test_shutdown_cancels_everything(self):
        self.sched.schedule_repeating("a", 20, lambda: None)
        self.sched.schedule_once("b", 500, lambda: None)
        self.sched.shutdown()
        self.assertFalse(self.sched.is_active("a"))
        self.assertFalse(self.sched.is_active("b"))


if __name__ == "__main__":
    unittest.main()
