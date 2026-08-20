# -*- coding: utf-8 -*-
"""内容源抓取：解析 RSS / Atom，供主动陪聊注入真实、可追溯的近期话题。

设计要点：

- 解析与网络分离，``parse_feed`` / ``collect_all`` 都是纯函数，方便注入桩做确定性测试。
- 兼容 RSS ``<item>`` 与 Atom ``<entry>``，按标签本地名匹配以忽略命名空间差异。
- 单个源失败（超时 / 非 200 / XML 损坏）只跳过该源，不影响其它源；全部失败时
  上层回退到本地哲学 / 冷知识话题池。
- 只保留标题、摘要、链接、来源，摘要去除 HTML 并截断，避免把整篇正文塞进 prompt。
"""

import re
import xml.etree.ElementTree as ET
from html import unescape

from ..config.constants import (
    CONTENT_FEED_FETCH_TIMEOUT,
    CONTENT_FEED_MAX_ITEMS_PER_CATEGORY,
    CONTENT_FEED_MAX_SUMMARY_LEN,
)

try:
    from PySide6.QtCore import QThread, Signal
except ImportError:  # 测试环境可能没有 Qt，纯函数仍可用
    QThread = object
    Signal = None

try:
    import requests
except ImportError:
    requests = None

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class FeedError(Exception):
    """抓取或解析内容源失败。"""


def _localname(tag):
    """去掉命名空间，只取标签本地名（如 ``{atom}entry`` -> ``entry``）。"""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _strip_html(text):
    text = _TAG_RE.sub(" ", text or "")
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def clean_summary(text, max_len=CONTENT_FEED_MAX_SUMMARY_LEN):
    text = _strip_html(text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def _parse_entry(el, source, category, max_summary_len):
    title = ""
    link = ""
    summary = ""
    published = ""
    guid = ""
    for child in list(el):
        name = _localname(child.tag)
        if name == "title" and not title:
            title = child.text or ""
        elif name == "link":
            href = child.get("href")
            if href:
                # Atom：优先 rel=alternate；否则先到先得
                if child.get("rel") in (None, "alternate") or not link:
                    link = href.strip()
            elif child.text and not link:
                link = child.text.strip()
        elif name in ("description", "summary", "content") and not summary:
            summary = child.text or ""
        elif name in ("pubDate", "published", "updated") and not published:
            published = (child.text or "").strip()
        elif name in ("guid", "id") and not guid:
            guid = (child.text or "").strip()

    title = _strip_html(title)
    summary = clean_summary(summary, max_summary_len)
    if not title and not summary:
        return None
    uid = guid or link or title
    return {
        "category": category,
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "published_at": published,
        "uid": uid,
    }


def parse_feed(xml_data, source, category,
               max_summary_len=CONTENT_FEED_MAX_SUMMARY_LEN):
    """把一段 RSS / Atom 文本解析成条目列表；无法解析时返回空列表。"""
    if not xml_data:
        return []
    # str 带 encoding 声明时 ET 会报错，统一转 bytes 再解析。
    if isinstance(xml_data, str):
        xml_data = xml_data.encode("utf-8")
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError:
        return []
    except Exception:
        return []

    items = []
    for el in root.iter():
        if _localname(el.tag) in ("item", "entry"):
            item = _parse_entry(el, source, category, max_summary_len)
            if item is not None:
                items.append(item)
    return items


def fetch_feed_items(url, source, category,
                     timeout=CONTENT_FEED_FETCH_TIMEOUT,
                     max_summary_len=CONTENT_FEED_MAX_SUMMARY_LEN):
    """抓取单个源并解析。网络 / 状态码异常抛 ``FeedError``。"""
    if requests is None:
        raise FeedError("缺少 requests 库，请先运行 install 脚本安装依赖。")
    try:
        resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=timeout)
    except requests.exceptions.Timeout:
        raise FeedError("请求超时：%s" % url)
    except requests.exceptions.ConnectionError:
        raise FeedError("连接失败：%s" % url)
    except Exception as exc:
        raise FeedError("抓取出错：%s" % str(exc)[:120])
    if resp.status_code != 200:
        raise FeedError("HTTP %s：%s" % (resp.status_code, url))
    return parse_feed(resp.content, source, category, max_summary_len)


def _dedup(items):
    seen = set()
    out = []
    for it in items:
        uid = it.get("uid")
        if uid in seen:
            continue
        seen.add(uid)
        out.append(it)
    return out


def collect_all(sources, timeout=CONTENT_FEED_FETCH_TIMEOUT,
                max_items=CONTENT_FEED_MAX_ITEMS_PER_CATEGORY,
                max_summary_len=CONTENT_FEED_MAX_SUMMARY_LEN,
                fetch_fn=None):
    """抓取所有类别的所有源，返回 ``{category: [item, ...]}``。

    单个源失败仅跳过该源；某类别全部失败则该类别不出现在结果中，
    由缓存里已有内容 / 本地话题池兜底。
    """
    fetch_fn = fetch_fn or fetch_feed_items
    result = {}
    for category, feeds in (sources or {}).items():
        items = []
        for source_name, url in feeds:
            try:
                items.extend(
                    fetch_fn(url, source_name, category, timeout, max_summary_len)
                )
            except FeedError:
                continue
            except Exception:
                continue
        if items:
            result[category] = _dedup(items)[:max_items]
    return result


if Signal is not None:

    class ContentRefreshWorker(QThread):
        """后台线程抓取 RSS，抓完把 ``{category: [item]}`` 交回主线程写入缓存。"""

        finished_ok = Signal(dict)
        failed = Signal(str)

        def __init__(self, sources, timeout=CONTENT_FEED_FETCH_TIMEOUT,
                     max_items=CONTENT_FEED_MAX_ITEMS_PER_CATEGORY,
                     max_summary_len=CONTENT_FEED_MAX_SUMMARY_LEN, parent=None):
            super().__init__(parent)
            self._sources = sources
            self._timeout = timeout
            self._max_items = max_items
            self._max_summary_len = max_summary_len

        def run(self):
            try:
                result = collect_all(
                    self._sources,
                    timeout=self._timeout,
                    max_items=self._max_items,
                    max_summary_len=self._max_summary_len,
                )
                self.finished_ok.emit(result)
            except Exception as exc:  # 兜底：抓取整体异常不该拖垮应用
                self.failed.emit(str(exc)[:150])
