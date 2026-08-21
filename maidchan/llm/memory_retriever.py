# -*- coding: utf-8 -*-
"""根据当前用户消息，从长期记忆中检索最相关的记忆。

混合召回策略：
1. 本地高置信匹配（不调 API）：把每条记忆的标签和内容里的实体片段拿来，
   看是否作为子串出现在用户消息里。命中即视为高置信，直接返回。
   这样「我今天想吃火鸡面」也能命中「用户喜欢吃火鸡面」。
2. 本地没有命中时，再异步调用 KeywordExtractWorker 让模型抽关键词/标签，
   兜住「你还记得我喜欢吃什么吗」这类没有实体词的自然提问。

未来可替换为向量检索。
"""

import json
import traceback

from PySide6.QtCore import QThread, Signal

from ..config.constants import DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .api_key import get_deepseek_api_key

try:
    import requests
except ImportError:
    requests = None

# 泛化填充词：出现在这些词里的候选片段不作为「实体关键词」用于本地匹配，
# 以免「喜欢 / 记得 / 什么」这类词把几乎所有记忆都误召回。
_STOPWORDS_SINGLE = set(
    "的了吗呢啊吧呀嘛哦噢哈嗯我你他她它们是在有和跟与也都就还又很太"
    "不没要会能可把被给让对从到去来说想吃喝看做过着的地得之其此该"
)
_STOPWORDS_MULTI = {
    "今天", "明天", "昨天", "前天", "后天", "现在", "刚才", "以前", "最近",
    "喜欢", "讨厌", "喜爱", "记得", "知道", "认识", "觉得", "感觉", "希望",
    "什么", "怎么", "为什么", "怎样", "如何", "多少", "哪里", "哪儿", "哪个",
    "可以", "可能", "应该", "已经", "还是", "或者", "而且", "但是", "所以",
    "因为", "如果", "我们", "你们", "他们", "咱们", "自己", "大家",
    "一个", "这个", "那个", "这样", "那样", "一下", "一点", "有点", "东西",
    "时候", "事情", "问题", "想要", "需要", "告诉", "帮我",
}

_MIN_TOKEN_LEN = 2


def _is_generic(token):
    """判断一个候选片段是否过于泛化，不适合用于本地高置信匹配。"""
    if not token:
        return True
    if token in _STOPWORDS_MULTI:
        return True
    if all(ch in _STOPWORDS_SINGLE for ch in token):
        return True
    for sw in _STOPWORDS_MULTI:
        if sw in token:
            return True
    return False


def _maximal_common_substrings(source, target, min_len=_MIN_TOKEN_LEN):
    """返回 source 中出现在 target 里、且不可再向两侧扩展的最长公共子串集合。

    以「最长」为单位可以避免把「喜欢吃」拆成碎片「欢吃」这类误命中：
    真正有意义的重叠会被完整保留，随后再统一过滤泛化词。
    """
    present = set()
    n = len(source)
    for i in range(n):
        for j in range(i + min_len, n + 1):
            sub = source[i:j]
            if sub in target:
                present.add(sub)
            else:
                # 更长的子串必然也不在 target 里，提前结束。
                break
    maximal = []
    for sub in sorted(present, key=len, reverse=True):
        if any(sub != other and sub in other for other in maximal):
            continue
        maximal.append(sub)
    return maximal


def extract_local_keywords(memory_store, user_msg, max_keywords=8):
    """本地高置信关键词抽取（不调 API）。

    以「记忆」为驱动：逐条取记忆的标签和内容，找出它与用户消息之间最长的公共
    片段。只有当这些片段是具体实体（过滤掉「喜欢/记得/什么」等泛化词）时才作为
    检索关键词。这样「我今天想吃火鸡面」能命中「用户喜欢吃火鸡面」，而「你还记得
    我喜欢吃什么吗」这类没有实体词的问法会本地落空、交给模型兜底。
    """
    if not user_msg:
        return []
    msg = user_msg.lower()
    found = []
    seen = set()

    def _collect(token):
        token = token.strip()
        if len(token) < _MIN_TOKEN_LEN or _is_generic(token):
            return
        low = token.lower()
        if low in seen:
            return
        seen.add(low)
        found.append(token)

    for m in memory_store.get_enabled():
        for tag in m.get("tags", []):
            t = str(tag).strip()
            if t.lower() in msg:
                _collect(t)
        content = m.get("content", "")
        for token in _maximal_common_substrings(content.lower(), msg):
            _collect(token)

    return found[:max_keywords]


KEYWORD_PROMPT = """\
从用户消息中提取用于检索用户长期记忆的关键词，最多 5 个。
优先输出具体实体（菜名、作品名、人名、地名、物品、活动等），
再补充相关领域标签（如 饮食、健康、情绪、工作、学习、人际、兴趣、计划）。
如果消息是纯闲聊 / 打招呼 / 无个人信息，返回空数组。

输出严格 JSON（不要加 markdown 包裹）：
{"keywords": ["关键词1", "关键词2"]}"""


class KeywordExtractWorker(QThread):
    """从用户消息提取关键词，用于记忆检索（本地未命中时的兜底）。"""
    extracted = Signal(list)  # list of keyword strings
    failed = Signal(str)

    def __init__(self, user_msg, parent=None):
        super().__init__(parent)
        self.user_msg = user_msg

    def run(self):
        if requests is None:
            self.extracted.emit([])
            return
        api_key = get_deepseek_api_key()
        if not api_key:
            self.extracted.emit([])
            return

        messages = [
            {"role": "system", "content": KEYWORD_PROMPT},
            {"role": "user", "content": self.user_msg},
        ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 100,
            "stream": False,
        }

        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=15
            )
            if resp.status_code != 200:
                self.extracted.emit([])
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            result = self._parse(content)
            self.extracted.emit(result)
        except Exception:
            traceback.print_exc()
            self.extracted.emit([])

    def _parse(self, text):
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            obj = json.loads(text)
            kw = obj.get("keywords", [])
            if isinstance(kw, list):
                return [str(k) for k in kw if k]
            return []
        except json.JSONDecodeError:
            return []


def retrieve_memories_sync(memory_store, keywords, limit=5):
    """同步检索：根据关键词从记忆库检索最相关的记忆。

    这是一个纯本地操作（不调 API），可以在主线程安全调用。
    """
    if not keywords:
        return []
    return memory_store.search_by_keywords(keywords, limit=limit)


def merge_keywords(*keyword_lists):
    """合并多组关键词，去重并保持顺序。"""
    seen = set()
    merged = []
    for kw_list in keyword_lists:
        for kw in kw_list or []:
            key = str(kw).strip()
            if not key:
                continue
            low = key.lower()
            if low in seen:
                continue
            seen.add(low)
            merged.append(key)
    return merged


def format_memories_for_prompt(memories):
    """将检索到的记忆格式化为注入 system prompt 的文本。"""
    if not memories:
        return ""
    lines = ["【可能相关的记忆（仅在与当前话题直接相关时才自然融入回答，不要主动罗列或强行关联）】"]
    for m in memories:
        content = m.get("content", "")
        mem_type = m.get("type", "")
        created = m.get("created_at", "")[:10]
        if mem_type == "episode":
            lines.append(f"- [{created}] {content}")
        else:
            lines.append(f"- {content}")
    lines.append("")
    return "\n".join(lines)
