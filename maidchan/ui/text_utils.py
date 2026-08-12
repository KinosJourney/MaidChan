# -*- coding: utf-8 -*-
"""文本拆句工具。"""


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
