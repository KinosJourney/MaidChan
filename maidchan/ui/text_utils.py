# -*- coding: utf-8 -*-
"""文本拆句工具。"""

import re

# 双语朗读：模型在中文回复后另起一行，用「[JA]」标记附上日语朗读文本。
# 兼容半角 / 全角括号及大小写，如 [JA] / 【ja】 / [ Ja ]。
_JA_MARKER_RE = re.compile(r"[\[【]\s*[Jj][Aa]\s*[\]】]")


def split_display_and_speech(content):
    """从模型回复中分离「气泡显示文本」与「日语朗读文本」。

    约定：模型在中文回复之后附上一行 ``[JA] <日本語>``。返回
    ``(display, speech)``；未找到标记时 ``speech`` 为 ``None``，``display`` 为原文。
    """
    if not content:
        return content, None
    m = _JA_MARKER_RE.search(content)
    if not m:
        return content.strip(), None
    display = content[: m.start()].strip()
    speech = content[m.end():].strip()
    return (display or content.strip()), (speech or None)


def split_sentences(text):
    """按中文/英文标点把文本拆成多句，便于逐句显示。"""
    result = []
    buf = ""
    enders = "。！？…!?\n"
    for ch in text:
        buf += ch
        if ch in enders:
            s = buf.strip()
            if s:
                result.append(s)
            buf = ""
    if buf.strip():
        result.append(buf.strip())
    # 合并过短的碎句
    merged = []
    for s in result:
        if merged and len(merged[-1]) < 6:
            merged[-1] = merged[-1] + s
        else:
            merged.append(s)
    return merged or [text]
