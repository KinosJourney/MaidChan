# -*- coding: utf-8 -*-
"""纯逻辑测试：JSON 存储、历史、档案、消息拼装、拆句。

这些测试不依赖 Qt，可直接运行。
"""

import os
import shutil
import tempfile
import unittest

from maidchan.storage.json_io import load_json, save_json
from maidchan.storage.history import HistoryStore
from maidchan.storage.profile import Profile
from maidchan.llm.messages import build_chat_messages
from maidchan.ui.text_utils import split_sentences


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        # 在仓库内创建临时目录，避免沙箱限制写系统临时目录。
        self.tmp = tempfile.mkdtemp(dir=REPO_ROOT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class JsonIoTest(TempDirTestCase):
    def test_roundtrip(self):
        path = os.path.join(self.tmp, "a.json")
        self.assertTrue(save_json(path, {"x": 1, "中文": "值"}))
        self.assertEqual(load_json(path, None), {"x": 1, "中文": "值"})

    def test_load_missing_returns_default(self):
        path = os.path.join(self.tmp, "missing.json")
        self.assertEqual(load_json(path, "DEF"), "DEF")

    def test_atomic_no_tmp_left(self):
        path = os.path.join(self.tmp, "b.json")
        save_json(path, [1, 2, 3])
        self.assertFalse(os.path.exists(path + ".tmp"))


class HistoryStoreTest(TempDirTestCase):
    def _store(self):
        return HistoryStore(os.path.join(self.tmp, "history.json"))

    def test_add_delete_clear(self):
        h = self._store()
        it = h.add("user", "你好")
        self.assertEqual(len(h.items), 1)
        self.assertTrue(h.delete(it["id"]))
        self.assertEqual(len(h.items), 0)
        h.add("user", "a")
        h.add("maid", "b")
        h.clear()
        self.assertEqual(h.items, [])

    def test_context_messages_role_mapping(self):
        h = self._store()
        h.add("user", "hi")
        h.add("maid", "yo")
        msgs = h.context_messages(12)
        self.assertEqual(msgs[0], {"role": "user", "content": "hi"})
        self.assertEqual(msgs[1], {"role": "assistant", "content": "yo"})

    def test_context_messages_truncation(self):
        h = self._store()
        for i in range(50):
            h.add("user", "u%d" % i)
            h.add("maid", "m%d" % i)
        msgs = h.context_messages(12)
        # 最多保留 max_turns*2 = 24 条
        self.assertEqual(len(msgs), 24)
        self.assertEqual(msgs[-1]["content"], "m49")

    def test_persistence_reload(self):
        path = os.path.join(self.tmp, "history.json")
        h1 = HistoryStore(path)
        h1.add("user", "记住我")
        h2 = HistoryStore(path)
        self.assertEqual(len(h2.items), 1)
        self.assertEqual(h2.items[0]["content"], "记住我")


class _FakeProfile:
    def __init__(self, prefix):
        self._prefix = prefix

    def as_prompt_prefix(self):
        return self._prefix


class _FakeHistory:
    def __init__(self, msgs):
        self._msgs = msgs
        self.seen = None

    def context_messages(self, max_turns):
        self.seen = max_turns
        return list(self._msgs)


class BuildMessagesTest(unittest.TestCase):
    def test_prefix_and_prompt_and_history(self):
        prof = _FakeProfile("【关于你的主人】\n昵称：A\n\n")
        hist = _FakeHistory([{"role": "user", "content": "hi"}])
        msgs = build_chat_messages(
            system_prompt="你是 Maid",
            profile=prof,
            history=hist,
            max_context_turns=7,
        )
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(
            msgs[0]["content"], "【关于你的主人】\n昵称：A\n\n你是 Maid"
        )
        self.assertEqual(msgs[1], {"role": "user", "content": "hi"})
        self.assertEqual(hist.seen, 7)

    def test_empty_prefix(self):
        prof = _FakeProfile("")
        hist = _FakeHistory([])
        msgs = build_chat_messages(
            system_prompt="P", profile=prof, history=hist
        )
        self.assertEqual(msgs, [{"role": "system", "content": "P"}])


class ProfilePrefixTest(TempDirTestCase):
    def test_as_prompt_prefix_ignores_empty(self):
        p = Profile.__new__(Profile)  # 不触发默认路径
        p.data = {"nickname": "小明", "birthday": "", "call_me": "主人"}
        prefix = p.as_prompt_prefix()
        self.assertIn("主人的昵称：小明", prefix)
        self.assertIn("主人希望你这样称呼TA：主人", prefix)
        self.assertNotIn("生日", prefix)

    def test_as_prompt_prefix_all_empty(self):
        p = Profile.__new__(Profile)
        p.data = {}
        self.assertEqual(p.as_prompt_prefix(), "")


class SplitSentencesTest(unittest.TestCase):
    def test_basic_split(self):
        out = split_sentences("你好呀，今天怎么样？我很好！")
        self.assertEqual(out, ["你好呀，今天怎么样？", "我很好！"])

    def test_merge_short_fragments(self):
        # 过短的碎句会被并入上一句
        out = split_sentences("好。今天天气非常不错呢！")
        self.assertEqual(out, ["好。今天天气非常不错呢！"])

    def test_no_punctuation(self):
        self.assertEqual(split_sentences("一段没有标点的话"), ["一段没有标点的话"])


if __name__ == "__main__":
    unittest.main()
