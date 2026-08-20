# -*- coding: utf-8 -*-
"""内容源抓取与缓存测试。

覆盖：RSS / Atom 解析、摘要清洗、单源失败隔离、抓取超时、缓存挑选、
跨重启去重、无网络时本地池兜底与循环复用。
"""

import os
import shutil
import tempfile
import unittest

from maidchan.core.content_feed import (
    FeedError,
    clean_summary,
    collect_all,
    fetch_feed_items,
    parse_feed,
)
from maidchan.storage.content_cache import ContentCache

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>示例新闻</title>
    <item>
      <title>标题一</title>
      <link>https://example.com/1</link>
      <description><![CDATA[<p>这是<b>第一条</b>摘要。</p>]]></description>
      <pubDate>Thu, 20 Aug 2026 09:00:00 +0800</pubDate>
      <guid>news-1</guid>
    </item>
    <item>
      <title>标题二</title>
      <link>https://example.com/2</link>
      <description>第二条摘要</description>
    </item>
  </channel>
</rss>"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>示例 Atom</title>
  <entry>
    <title>原子标题</title>
    <link rel="alternate" href="https://example.com/atom/1"/>
    <summary>原子摘要内容</summary>
    <id>atom-1</id>
    <updated>2026-08-20T09:00:00Z</updated>
  </entry>
</feed>"""


class ParseFeedTest(unittest.TestCase):
    def test_parse_rss(self):
        items = parse_feed(RSS_SAMPLE, "示例新闻", "news")
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["title"], "标题一")
        self.assertEqual(first["link"], "https://example.com/1")
        self.assertEqual(first["source"], "示例新闻")
        self.assertEqual(first["category"], "news")
        self.assertEqual(first["uid"], "news-1")
        # HTML 标签被清除
        self.assertNotIn("<", first["summary"])
        self.assertIn("第一条", first["summary"])

    def test_parse_atom(self):
        items = parse_feed(ATOM_SAMPLE, "示例 Atom", "gossip")
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["title"], "原子标题")
        self.assertEqual(it["link"], "https://example.com/atom/1")
        self.assertEqual(it["summary"], "原子摘要内容")
        self.assertEqual(it["uid"], "atom-1")

    def test_uid_falls_back_to_link_then_title(self):
        items = parse_feed(RSS_SAMPLE, "s", "news")
        # 第二条无 guid，用 link 作 uid
        self.assertEqual(items[1]["uid"], "https://example.com/2")

    def test_broken_xml_returns_empty(self):
        self.assertEqual(parse_feed("<not xml", "s", "news"), [])
        self.assertEqual(parse_feed("", "s", "news"), [])

    def test_clean_summary_truncates(self):
        text = clean_summary("啊" * 500, max_len=10)
        self.assertTrue(text.endswith("…"))
        self.assertLessEqual(len(text), 11)


class FetchFeedTest(unittest.TestCase):
    def test_status_error_raises(self):
        class Resp:
            status_code = 404
            content = b""

        import maidchan.core.content_feed as cf
        orig = cf.requests
        try:
            cf.requests = _FakeRequests(Resp())
            with self.assertRaises(FeedError):
                fetch_feed_items("https://x", "s", "news")
        finally:
            cf.requests = orig

    def test_timeout_raises(self):
        import maidchan.core.content_feed as cf
        orig = cf.requests
        try:
            cf.requests = _FakeRequests(None, raise_timeout=True)
            with self.assertRaises(FeedError):
                fetch_feed_items("https://x", "s", "news")
        finally:
            cf.requests = orig


class CollectAllTest(unittest.TestCase):
    def test_source_failure_isolated(self):
        sources = {
            "news": [("好源", "https://ok"), ("坏源", "https://bad")],
        }

        def fake_fetch(url, source, category, timeout, max_len):
            if "bad" in url:
                raise FeedError("boom")
            return [{"uid": "a", "title": "t", "summary": "s",
                     "link": url, "source": source, "category": category,
                     "published_at": ""}]

        result = collect_all(sources, fetch_fn=fake_fetch)
        self.assertIn("news", result)
        self.assertEqual(len(result["news"]), 1)

    def test_all_fail_category_absent(self):
        sources = {"news": [("坏源", "https://bad")]}

        def fake_fetch(*a, **k):
            raise FeedError("boom")

        result = collect_all(sources, fetch_fn=fake_fetch)
        self.assertNotIn("news", result)

    def test_dedup_by_uid(self):
        sources = {"news": [("s1", "https://1"), ("s2", "https://2")]}

        def fake_fetch(url, source, category, timeout, max_len):
            return [{"uid": "same", "title": "t", "summary": "s",
                     "link": url, "source": source, "category": category,
                     "published_at": ""}]

        result = collect_all(sources, fetch_fn=fake_fetch)
        self.assertEqual(len(result["news"]), 1)


class _FakeRequests:
    class exceptions:
        class Timeout(Exception):
            pass

        class ConnectionError(Exception):
            pass

    def __init__(self, resp, raise_timeout=False):
        self._resp = resp
        self._raise_timeout = raise_timeout

    def get(self, *args, **kwargs):
        if self._raise_timeout:
            raise self.exceptions.Timeout()
        return self._resp


class ContentCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=REPO_ROOT)
        self.path = os.path.join(self.tmp, "content_cache.json")
        self.pools = {
            "philosophy": [
                {"source": "池", "title": "P1", "summary": "s1"},
                {"source": "池", "title": "P2", "summary": "s2"},
            ],
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_local_pool_available_without_network(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        self.assertTrue(cache.has_content("philosophy"))
        item = cache.pick("philosophy")
        self.assertIsNotNone(item)
        self.assertIn(item["title"], ("P1", "P2"))

    def test_empty_category_returns_none(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        self.assertIsNone(cache.pick("news"))

    def test_update_replaces_category(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        cache.update({"news": [
            {"uid": "n1", "title": "N1", "summary": "s", "source": "src"},
        ]})
        self.assertTrue(cache.has_content("news"))
        self.assertEqual(cache.pick("news")["title"], "N1")

    def test_empty_update_does_not_wipe(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        cache.update({"news": [
            {"uid": "n1", "title": "N1", "summary": "s", "source": "src"},
        ]})
        cache.update({"news": []})
        self.assertTrue(cache.has_content("news"))

    def test_mark_used_avoids_repeat(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        first = cache.pick("philosophy")
        cache.mark_used(first)
        second = cache.pick("philosophy")
        self.assertNotEqual(first["title"], second["title"])

    def test_cycle_after_exhausting_pool(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        cache.mark_used(cache.pick("philosophy"))
        remaining = cache.pick("philosophy")
        cache.mark_used(remaining)
        # 两条都聊过后仍能取到（循环复用）
        again = cache.pick("philosophy")
        self.assertIsNotNone(again)

    def test_used_persist_across_restart(self):
        cache = ContentCache(self.path, local_pools=self.pools)
        cache.update({"news": [
            {"uid": "n1", "title": "N1", "summary": "s", "source": "src"},
            {"uid": "n2", "title": "N2", "summary": "s", "source": "src"},
        ]})
        cache.mark_used({"uid": "n1"})

        cache2 = ContentCache(self.path, local_pools=self.pools)
        # n1 已聊过，重启后应挑到 n2
        picked = cache2.pick("news")
        self.assertEqual(picked["uid"], "n2")


if __name__ == "__main__":
    unittest.main()
