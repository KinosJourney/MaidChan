# -*- coding: utf-8 -*-
"""混合记忆召回测试：本地高置信匹配、LLM 关键词兜底降级、关键词合并。

覆盖“记忆里有知识但关联不上”的核心修复：自然中文问法也能召回。
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from maidchan.storage.memory import MemoryStore
from maidchan.llm import memory_retriever
from maidchan.llm import memory_extractor
from maidchan.llm.memory_extractor import MemoryExtractWorker, EXTRACTION_PROMPT
from maidchan.llm.memory_retriever import (
    KeywordExtractWorker,
    extract_local_keywords,
    merge_keywords,
    retrieve_memories_sync,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LocalKeywordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=REPO_ROOT)
        self.store = MemoryStore(os.path.join(self.tmp, "memories.json"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _contents(self, memories):
        return [m["content"] for m in memories]

    def test_entity_in_long_sentence(self):
        """长中文句包含实体：我今天想吃火鸡面 -> 用户喜欢吃火鸡面。"""
        self.store.add("preference", "用户喜欢吃火鸡面", tags=["饮食", "辣味"])
        kws = extract_local_keywords(self.store, "我今天想吃火鸡面")
        self.assertTrue(kws, "应从长句中抽出实体关键词")
        results = retrieve_memories_sync(self.store, kws)
        self.assertEqual(len(results), 1)
        self.assertIn("火鸡面", results[0]["content"])

    def test_exact_entity(self):
        self.store.add("preference", "用户喜欢吃火鸡面", tags=["饮食"])
        kws = extract_local_keywords(self.store, "火鸡面")
        results = retrieve_memories_sync(self.store, kws)
        self.assertEqual(len(results), 1)

    def test_tag_match(self):
        """领域/实体标签命中：推荐一部动漫 -> 命中带动漫标签的记忆。"""
        self.store.add("preference", "用户喜欢看钢之炼金术师", tags=["动漫", "喜好"])
        kws = extract_local_keywords(self.store, "推荐一部动漫")
        self.assertIn("动漫", kws)
        results = retrieve_memories_sync(self.store, kws)
        self.assertEqual(len(results), 1)

    def test_generic_phrasing_no_false_match(self):
        """泛化问法不误命中：碎片/泛化词不应把无关记忆拉出来。"""
        self.store.add("preference", "用户喜欢吃火鸡面", tags=["饮食"])
        self.store.add("preference", "用户讨厌香菜", tags=["饮食"])
        kws = extract_local_keywords(self.store, "你还记得我喜欢吃什么吗？")
        self.assertEqual(kws, [], "没有实体词的泛化提问应本地落空，交给模型兜底")

    def test_greeting_no_match(self):
        self.store.add("preference", "用户喜欢吃火鸡面", tags=["饮食"])
        self.assertEqual(extract_local_keywords(self.store, "在吗？今天天气不错"), [])

    def test_disabled_memory_not_recalled(self):
        item = self.store.add("preference", "用户喜欢吃火鸡面", tags=["饮食"])
        item["enabled"] = False
        self.store.save()
        kws = extract_local_keywords(self.store, "我想吃火鸡面")
        self.assertEqual(kws, [])
        self.assertEqual(retrieve_memories_sync(self.store, ["火鸡面"]), [])

    def test_empty_message(self):
        self.store.add("preference", "用户喜欢吃火鸡面")
        self.assertEqual(extract_local_keywords(self.store, ""), [])


class MergeKeywordsTest(unittest.TestCase):
    def test_dedup_and_order(self):
        merged = merge_keywords(["火鸡面", "饮食"], ["饮食", "辣味", ""])
        self.assertEqual(merged, ["火鸡面", "饮食", "辣味"])

    def test_case_insensitive_dedup(self):
        self.assertEqual(merge_keywords(["Anime"], ["anime"]), ["Anime"])

    def test_all_empty(self):
        self.assertEqual(merge_keywords([], None), [])


class RetrieveSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=REPO_ROOT)
        self.store = MemoryStore(os.path.join(self.tmp, "memories.json"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_keywords(self):
        self.store.add("preference", "用户喜欢吃火鸡面")
        self.assertEqual(retrieve_memories_sync(self.store, []), [])


class KeywordExtractWorkerTest(unittest.TestCase):
    def test_parse_plain_json(self):
        w = KeywordExtractWorker("随便")
        self.assertEqual(w._parse('{"keywords": ["饮食", "火鸡面"]}'), ["饮食", "火鸡面"])

    def test_parse_markdown_wrapped(self):
        w = KeywordExtractWorker("随便")
        text = "```json\n{\"keywords\": [\"动漫\"]}\n```"
        self.assertEqual(w._parse(text), ["动漫"])

    def test_parse_invalid_returns_empty(self):
        w = KeywordExtractWorker("随便")
        self.assertEqual(w._parse("not json"), [])

    def test_run_without_requests_emits_empty(self):
        """降级：缺少 requests（或网络不可用）时安全返回空关键词，不阻断聊天。"""
        original = memory_retriever.requests
        memory_retriever.requests = None
        try:
            w = KeywordExtractWorker("我今天想吃火鸡面")
            captured = []
            w.extracted.connect(captured.append)
            w.run()
            self.assertEqual(captured, [[]])
        finally:
            memory_retriever.requests = original


class ExtractorAntiFabricationTest(unittest.TestCase):
    """记忆提取的防幻觉：只记用户明说的，不从角色回复脑补。"""

    def test_prompt_forbids_fabrication(self):
        self.assertIn("绝不编造", EXTRACTION_PROMPT)
        self.assertIn("角色回复", EXTRACTION_PROMPT)
        self.assertIn("宁可漏记", EXTRACTION_PROMPT)

    def _run_and_capture(self, payload):
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = payload
        captured, fails = [], []
        with patch.object(memory_extractor, "requests") as mreq, \
                patch.object(memory_extractor, "get_deepseek_api_key",
                             return_value="key"):
            mreq.post.return_value = fake_resp
            w = MemoryExtractWorker("我喜欢吃火鸡面", "好的，记住啦～")
            w.extracted.connect(captured.append)
            w.failed.connect(fails.append)
            w.run()
        return captured, fails

    def test_should_remember_false_emits_empty(self):
        payload = {"choices": [{"message": {"content": json.dumps(
            {"should_remember": False, "memories": []})}}]}
        captured, fails = self._run_and_capture(payload)
        self.assertEqual(captured, [[]])
        self.assertEqual(fails, [])

    def test_grounded_memory_emitted(self):
        mems = [{"type": "preference", "content": "用户喜欢吃火鸡面",
                 "tags": ["饮食"], "importance": 0.5}]
        payload = {"choices": [{"message": {"content": json.dumps(
            {"should_remember": True, "memories": mems})}}]}
        captured, fails = self._run_and_capture(payload)
        self.assertEqual(captured, [mems])
        self.assertEqual(fails, [])


if __name__ == "__main__":
    unittest.main()
