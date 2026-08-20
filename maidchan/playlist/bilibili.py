# -*- coding: utf-8 -*-
"""解析 B 站合集链接、拉取稿件列表并随机挑选。"""

import time
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QThread, Signal

try:
    import requests
except ImportError:
    requests = None

COLLECTION_API = (
    "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
)
VIDEO_URL = "https://www.bilibili.com/video/%s"
CACHE_TTL_SEC = 600
PAGE_SIZE = 50
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Accept": "application/json",
}

# (mid, season_id) -> (fetched_at, videos)
_cache = {}


class CollectionError(Exception):
    """合集链接无效，或接口返回空列表 / 错误。"""


def parse_collection_url(url):
    """从合集页 URL 解析 (mid, season_id)。

    支持两种格式：
    ``https://space.bilibili.com/{mid}/channel/collectiondetail?sid={sid}``
    ``https://space.bilibili.com/{mid}/lists/{sid}?type=season``
    """
    if not url or not str(url).strip():
        raise CollectionError("还没有填写合集链接哦～")
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in ("http", "https"):
        raise CollectionError("合集链接需要是 http 或 https。")
    host = (parsed.netloc or "").lower()
    if "bilibili.com" not in host:
        raise CollectionError("目前只支持 B 站合集链接。")

    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    mid = path_parts[0] if path_parts else None

    sid = None
    if len(path_parts) >= 3 and path_parts[1] == "lists":
        sid = path_parts[2]
    else:
        qs = parse_qs(parsed.query)
        sid = (qs.get("sid") or [None])[0]

    if not (mid and mid.isdigit() and sid and str(sid).isdigit()):
        raise CollectionError(
            "没认出这是合集链接。请使用类似\n"
            "space.bilibili.com/数字/lists/数字?type=season\n"
            "或 space.bilibili.com/数字/channel/collectiondetail?sid=数字"
        )
    return mid, str(sid)


def short_title(title, max_len=22):
    """气泡里用的短标题：取第一个分隔段并截断。"""
    text = (title or "").strip() or "这一条"
    for sep in ("丨", "｜", "|"):
        if sep in text:
            text = text.split(sep, 1)[0].strip() or text
            break
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def pick_random(videos, exclude_bvid=None):
    """从列表中随机挑一条；尽量不连续重复同一条。"""
    import random

    if not videos:
        raise CollectionError("合集里还没有视频。")
    candidates = videos
    if exclude_bvid and len(videos) > 1:
        filtered = [v for v in videos if v.get("bvid") != exclude_bvid]
        if filtered:
            candidates = filtered
    return random.choice(candidates)


def fetch_collection_videos(mid, season_id):
    """拉取合集内全部稿件，结果缓存几分钟。返回 [{bvid, title, url}, ...]。"""
    key = (str(mid), str(season_id))
    cached = _cache.get(key)
    if cached:
        fetched_at, videos = cached
        if time.time() - fetched_at < CACHE_TTL_SEC and videos:
            return videos

    videos = _download_all_pages(mid, season_id)
    _cache[key] = (time.time(), videos)
    return videos


def clear_cache():
    _cache.clear()


def _download_all_pages(mid, season_id):
    if requests is None:
        raise CollectionError("缺少 requests 库，请先运行 install 脚本安装依赖。")

    videos = []
    page_num = 1
    total = None
    while True:
        payload = _request_page(mid, season_id, page_num)
        archives = payload.get("archives") or []
        for item in archives:
            bvid = item.get("bvid")
            if not bvid:
                continue
            videos.append(
                {
                    "bvid": bvid,
                    "title": item.get("title") or bvid,
                    "url": VIDEO_URL % bvid,
                }
            )
        page = payload.get("page") or {}
        total = page.get("total", total)
        if not archives:
            break
        if total is not None and len(videos) >= int(total):
            break
        page_num += 1
        if page_num > 50:
            break

    if not videos:
        raise CollectionError("合集里还没有视频。")
    return videos


def _request_page(mid, season_id, page_num):
    try:
        resp = requests.get(
            COLLECTION_API,
            params={
                "mid": mid,
                "season_id": season_id,
                "page_num": page_num,
                "page_size": PAGE_SIZE,
                "sort_reverse": "false",
            },
            headers=_BROWSER_HEADERS,
            timeout=12,
        )
    except requests.exceptions.Timeout:
        raise CollectionError("合集加载超时了，请稍后再试～")
    except requests.exceptions.ConnectionError:
        raise CollectionError("连不上网络，没法翻合集呢。")
    except Exception as exc:
        raise CollectionError("翻合集出错了：%s" % str(exc)[:120])

    if resp.status_code != 200:
        raise CollectionError("合集接口返回错误 %s。" % resp.status_code)

    try:
        data = resp.json()
    except Exception:
        raise CollectionError("合集接口返回了看不懂的内容。")

    if data.get("code") != 0:
        raise CollectionError(
            "合集接口失败：%s" % (data.get("message") or data.get("code"))
        )
    return data.get("data") or {}


class PlaylistWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, playlist_url, exclude_bvid=None, parent=None):
        super().__init__(parent)
        self.playlist_url = playlist_url
        self.exclude_bvid = exclude_bvid

    def run(self):
        try:
            mid, season_id = parse_collection_url(self.playlist_url)
            videos = fetch_collection_videos(mid, season_id)
            video = pick_random(videos, self.exclude_bvid)
            self.finished_ok.emit(video)
        except CollectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit("翻合集出错了：%s" % str(exc)[:120])
