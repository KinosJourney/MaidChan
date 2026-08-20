# -*- coding: utf-8 -*-
"""待办解析 Worker 测试（mock requests，不实际联网）。

覆盖：标准 JSON、markdown 包裹、含糊时间、过去时间、非待办语音、接口错误。
"""

import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

import requests as real_requests


def _resp(content, status=200):
    """构造一个模拟 DeepSeek Chat 返回。"""
    return MagicMock(
        status_code=status,
        json=MagicMock(return_value={
            "choices": [{"message": {"content": content}}]
        }),
    )


class TodoParseWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def _run(self, model_content, text="提醒我下午三点开会",
             now=datetime(2026, 8, 20, 10, 0, 0)):
        from maidchan.llm.todo_extractor import TodoParseWorker

        worker = TodoParseWorker(text, now)
        results = {"parsed": [], "failed": []}
        worker.parsed.connect(lambda d: results["parsed"].append(d))
        worker.failed.connect(lambda e: results["failed"].append(e))
        with patch("maidchan.llm.todo_extractor.get_deepseek_api_key",
                   return_value="sk-test"):
            with patch("maidchan.llm.todo_extractor.requests") as mock_req:
                mock_req.post.return_value = _resp(model_content)
                mock_req.exceptions = real_requests.exceptions
                worker.run()
        return results

    def test_standard_json(self):
        r = self._run('{"is_todo": true, "content": "开会", "due_at": "2026-08-20 15:00:00"}')
        self.assertEqual(r["failed"], [])
        self.assertEqual(len(r["parsed"]), 1)
        self.assertTrue(r["parsed"][0]["is_todo"])
        self.assertEqual(r["parsed"][0]["content"], "开会")
        self.assertEqual(r["parsed"][0]["due_at"], "2026-08-20 15:00:00")

    def test_markdown_wrapped_json(self):
        content = (
            "```json\n"
            '{"is_todo": true, "content": "吃药", "due_at": "2026-08-20 20:00:00"}\n'
            "```"
        )
        r = self._run(content)
        self.assertEqual(len(r["parsed"]), 1)
        self.assertTrue(r["parsed"][0]["is_todo"])
        self.assertEqual(r["parsed"][0]["content"], "吃药")

    def test_not_a_todo(self):
        r = self._run('{"is_todo": false, "content": "", "due_at": ""}',
                      text="今天天气真好啊")
        self.assertEqual(len(r["parsed"]), 1)
        self.assertFalse(r["parsed"][0]["is_todo"])

    def test_past_time_treated_as_non_todo(self):
        # 模型给了过去时间，应被归一化为非待办
        r = self._run('{"is_todo": true, "content": "开会", "due_at": "2026-08-20 09:00:00"}')
        self.assertEqual(len(r["parsed"]), 1)
        self.assertFalse(r["parsed"][0]["is_todo"])

    def test_time_without_seconds(self):
        # 模型常省略秒，应能容忍解析（复现「下午4点半」丢失的场景）
        r = self._run(
            '{"is_todo": true, "content": "出去锻炼", "due_at": "2026-08-20 16:30"}',
            text="提醒我今天下午4点半出去锻炼",
        )
        self.assertEqual(len(r["parsed"]), 1)
        self.assertTrue(r["parsed"][0]["is_todo"])
        self.assertEqual(r["parsed"][0]["content"], "出去锻炼")
        self.assertEqual(r["parsed"][0]["due_at"], "2026-08-20 16:30:00")

    def test_iso_t_separator(self):
        r = self._run('{"is_todo": true, "content": "开会", "due_at": "2026-08-20T15:00:00"}')
        self.assertEqual(len(r["parsed"]), 1)
        self.assertTrue(r["parsed"][0]["is_todo"])
        self.assertEqual(r["parsed"][0]["due_at"], "2026-08-20 15:00:00")

    def test_slash_date_without_seconds(self):
        r = self._run('{"is_todo": true, "content": "吃药", "due_at": "2026/08/20 20:00"}')
        self.assertEqual(len(r["parsed"]), 1)
        self.assertTrue(r["parsed"][0]["is_todo"])
        self.assertEqual(r["parsed"][0]["due_at"], "2026-08-20 20:00:00")

    def test_vague_time_treated_as_non_todo(self):
        # 无法解析的时间格式
        r = self._run('{"is_todo": true, "content": "开会", "due_at": "改天"}')
        self.assertEqual(len(r["parsed"]), 1)
        self.assertFalse(r["parsed"][0]["is_todo"])

    def test_empty_content_treated_as_non_todo(self):
        r = self._run('{"is_todo": true, "content": "", "due_at": "2026-08-20 15:00:00"}')
        self.assertEqual(len(r["parsed"]), 1)
        self.assertFalse(r["parsed"][0]["is_todo"])

    def test_bad_json_fails(self):
        r = self._run("this is not json at all")
        self.assertEqual(len(r["failed"]), 1)
        self.assertEqual(r["parsed"], [])

    def test_api_error_status(self):
        from maidchan.llm.todo_extractor import TodoParseWorker

        worker = TodoParseWorker("提醒我开会", datetime(2026, 8, 20, 10, 0, 0))
        results = {"parsed": [], "failed": []}
        worker.parsed.connect(lambda d: results["parsed"].append(d))
        worker.failed.connect(lambda e: results["failed"].append(e))
        with patch("maidchan.llm.todo_extractor.get_deepseek_api_key",
                   return_value="sk-test"):
            with patch("maidchan.llm.todo_extractor.requests") as mock_req:
                mock_req.post.return_value = MagicMock(status_code=500)
                mock_req.exceptions = real_requests.exceptions
                worker.run()
        self.assertEqual(len(results["failed"]), 1)
        self.assertIn("500", results["failed"][0])

    def test_no_api_key_fails(self):
        from maidchan.llm.todo_extractor import TodoParseWorker

        worker = TodoParseWorker("提醒我开会", datetime(2026, 8, 20, 10, 0, 0))
        results = {"parsed": [], "failed": []}
        worker.parsed.connect(lambda d: results["parsed"].append(d))
        worker.failed.connect(lambda e: results["failed"].append(e))
        with patch("maidchan.llm.todo_extractor.get_deepseek_api_key",
                   return_value=""):
            worker.run()
        self.assertEqual(len(results["failed"]), 1)
        self.assertIn("API Key", results["failed"][0])


if __name__ == "__main__":
    unittest.main()
