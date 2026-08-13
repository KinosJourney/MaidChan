# -*- coding: utf-8 -*-
"""合集播放：URL 解析、短标题、随机挑选、接口拉取。"""

import unittest
from unittest.mock import patch

from maidchan.playlist.bilibili import (
    CollectionError,
    clear_cache,
    fetch_collection_videos,
    parse_collection_url,
    pick_random,
    short_title,
)
from maidchan.playlist.hotkey import hotkey_display, parse_hotkey


SAMPLE_URL = (
    "https://space.bilibili.com/599873511/channel/collectiondetail"
    "?sid=6665575&spm_id_from=333.788.0.0"
)


class ParseCollectionUrlTest(unittest.TestCase):
    def test_standard_url_with_tracking(self):
        mid, sid = parse_collection_url(SAMPLE_URL)
        self.assertEqual(mid, "599873511")
        self.assertEqual(sid, "6665575")

    def test_rejects_video_url(self):
        with self.assertRaises(CollectionError):
            parse_collection_url("https://www.bilibili.com/video/BV1KM1KB3EnZ")

    def test_rejects_empty(self):
        with self.assertRaises(CollectionError):
            parse_collection_url("  ")

    def test_rejects_non_https(self):
        with self.assertRaises(CollectionError):
            parse_collection_url("javascript:alert(1)")


class ShortTitleTest(unittest.TestCase):
    def test_keeps_first_segment(self):
        self.assertEqual(
            short_title("4小时沉浸式在姜岛海边学习丨一起高效学习丨番茄钟"),
            "4小时沉浸式在姜岛海边学习",
        )

    def test_truncates_long_title(self):
        title = "这是一个没有任何分隔符但是非常非常非常长的标题"
        out = short_title(title, max_len=10)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 11)


class PickRandomTest(unittest.TestCase):
    def test_avoids_last_when_possible(self):
        videos = [{"bvid": "a"}, {"bvid": "b"}]
        for _ in range(12):
            self.assertEqual(pick_random(videos, "a")["bvid"], "b")

    def test_single_item_ignores_exclude(self):
        videos = [{"bvid": "a", "title": "only"}]
        self.assertEqual(pick_random(videos, "a")["bvid"], "a")

    def test_empty_raises(self):
        with self.assertRaises(CollectionError):
            pick_random([])


class ParseHotkeyTest(unittest.TestCase):
    def test_ctrl_shift_p(self):
        mods, letter = parse_hotkey("Ctrl+Shift+P")
        self.assertEqual(mods, {"ctrl", "shift"})
        self.assertEqual(letter, "P")

    def test_display_contains_letter(self):
        self.assertIn("P", hotkey_display("Ctrl+Shift+P"))


class FakeResp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class FetchCollectionTest(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_maps_bvid_and_title(self):
        payload = {
            "code": 0,
            "message": "OK",
            "data": {
                "archives": [
                    {"bvid": "BV1aaa", "title": "第一集丨学习"},
                    {"bvid": "BV1bbb", "title": "第二集"},
                ],
                "page": {"page_num": 1, "page_size": 50, "total": 2},
            },
        }

        def fake_get(*_args, **_kwargs):
            return FakeResp(payload)

        with patch("maidchan.playlist.bilibili.requests.get", fake_get):
            videos = fetch_collection_videos("599873511", "6665575")
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0]["bvid"], "BV1aaa")
        self.assertEqual(
            videos[0]["url"], "https://www.bilibili.com/video/BV1aaa"
        )

    def test_api_error(self):
        def fake_get(*_args, **_kwargs):
            return FakeResp({"code": -352, "message": "-352"})

        with patch("maidchan.playlist.bilibili.requests.get", fake_get):
            with self.assertRaises(CollectionError):
                fetch_collection_videos("1", "2")


if __name__ == "__main__":
    unittest.main()
