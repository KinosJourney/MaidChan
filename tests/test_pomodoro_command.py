# -*- coding: utf-8 -*-
"""语音番茄钟指令解析测试。"""

import unittest

from maidchan.core.pomodoro_command import parse_pomodoro_command


def _start(minutes=None, rest=None):
    return {"action": "start", "minutes": minutes, "rest_minutes": rest}


class PomodoroCommandParseTest(unittest.TestCase):
    def test_start_basic(self):
        self.assertEqual(parse_pomodoro_command("开始番茄钟"), _start())
        self.assertEqual(parse_pomodoro_command("帮我开始一个番茄钟"), _start())
        self.assertEqual(parse_pomodoro_command("开启番茄钟吧"), _start())
        self.assertEqual(parse_pomodoro_command("来一轮番茄"), _start())
        self.assertEqual(parse_pomodoro_command("帮我开个番茄钟"), _start())
        self.assertEqual(parse_pomodoro_command("番茄钟"), _start())

    def test_start_with_minutes(self):
        self.assertEqual(parse_pomodoro_command("开始25分钟番茄钟"), _start(25))
        self.assertEqual(parse_pomodoro_command("专注25分钟"), _start(25))
        self.assertEqual(parse_pomodoro_command("番茄钟二十五分钟"), _start(25))
        self.assertEqual(parse_pomodoro_command("开始半小时专注"), _start(30))
        self.assertEqual(parse_pomodoro_command("专注一小时"), _start(60))

    def test_start_with_rest(self):
        self.assertEqual(
            parse_pomodoro_command("开始25分钟专注5分钟休息"),
            _start(25, 5),
        )
        self.assertEqual(
            parse_pomodoro_command("专注四十五分钟休息十分钟"),
            _start(45, 10),
        )

    def test_work_methods(self):
        self.assertEqual(parse_pomodoro_command("用番茄工作法"), _start(25, 5))
        self.assertEqual(parse_pomodoro_command("五十二十七法则"), _start(52, 17))
        self.assertEqual(parse_pomodoro_command("52/17法则"), _start(52, 17))
        self.assertEqual(parse_pomodoro_command("九十分钟周期"), _start(90, 25))

    def test_stt_alias_and_fullwidth(self):
        self.assertEqual(parse_pomodoro_command("开始番茄种"), _start())
        self.assertEqual(parse_pomodoro_command("专注２５分钟"), _start(25))

    def test_open_pause_resume_cancel_skip(self):
        self.assertEqual(
            parse_pomodoro_command("打开番茄钟")["action"], "open"
        )
        self.assertEqual(
            parse_pomodoro_command("打开番茄钟设置")["action"], "open"
        )
        self.assertEqual(
            parse_pomodoro_command("暂停专注")["action"], "pause"
        )
        self.assertEqual(
            parse_pomodoro_command("继续番茄钟")["action"], "resume"
        )
        self.assertEqual(
            parse_pomodoro_command("取消番茄钟")["action"], "cancel"
        )
        self.assertEqual(
            parse_pomodoro_command("关掉番茄钟")["action"], "cancel"
        )
        self.assertEqual(
            parse_pomodoro_command("跳过休息")["action"], "skip_rest"
        )

    def test_open_does_not_steal_start(self):
        self.assertEqual(
            parse_pomodoro_command("打开番茄钟开始专注"), _start()
        )

    def test_rejects_chat_and_todos(self):
        self.assertIsNone(parse_pomodoro_command("今天天气真好"))
        self.assertIsNone(parse_pomodoro_command("番茄炒蛋"))
        self.assertIsNone(parse_pomodoro_command("番茄钟是什么"))
        self.assertIsNone(parse_pomodoro_command("提醒我25分钟后休息"))
        self.assertIsNone(parse_pomodoro_command("提醒我下午三点开会"))
        self.assertIsNone(parse_pomodoro_command("我今天要好好学习"))
        self.assertIsNone(parse_pomodoro_command(""))

    def test_clamps_overlong_minutes(self):
        self.assertEqual(parse_pomodoro_command("专注200分钟")["minutes"], 120)


if __name__ == "__main__":
    unittest.main()
