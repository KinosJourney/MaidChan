# -*- coding: utf-8 -*-
"""从语音识别文本里解析番茄钟指令。

走关键词 / 正则，不额外调用模型：命中则由桌宠直接操作番茄钟，
未命中则保持原有「当闲聊发送 + 后台解析待办」路径。
"""

import re

from ..config.constants import (
    POMODORO_MAX_MINUTES,
    POMODORO_MIN_MINUTES,
    REST_MAX_MINUTES,
    REST_MIN_MINUTES,
    WORK_METHODS,
)

# 语音识别常见把「钟」听成「种 / 中」
_STT_ALIASES = (
    ("番茄种", "番茄钟"),
    ("番茄中", "番茄钟"),
    ("番前钟", "番茄钟"),
)

_CN_DIGITS = {
    "零": 0, "〇": 0, "○": 0,
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_FW_TRANS = str.maketrans(
    "０１２３４５６７８９，。！？、；：／",
    "0123456789,.!?、;:/",
)

# 去掉礼貌词、语气词后，再判断整句是不是指令（长词优先，避免「来一轮」被切成「来一」+「轮」）
_FILLER = re.compile(
    r"(请你?|麻烦你?|帮我|给我|为我|我想要?|我要|"
    r"来一轮|来一个|来个|来一|"
    r"开一下|开个|定个|定一个|"
    r"一下|一个|一轮|用一下|用|"
    r"好的|嗯|啊|呀|哦|呢|吧|谢谢)"
)

# 指令词汇；去掉它们之后若还剩明显闲聊内容，则不当指令
_COMMAND_TOKENS = re.compile(
    r"(请你?|麻烦你?|帮我|给我|为我|我想要?|我要|来一轮|来一个|来个|来一|"
    r"开一下|开个|定个|定一个|一下|一个|一轮|用一下|用|"
    r"好的|嗯|啊|呀|哦|呢|吧|谢谢|"
    r"开始|开启|启动|打开|暂停|继续|恢复|取消|关掉|关闭|停止|结束|退出|"
    r"跳过|休息|专注|番茄钟|番茄工作法|番茄|分钟|小时|个小时|"
    r"工作法|法则|周期|倒计时|设置|面板|窗口|模式|"
    r"半|零|〇|○|一|二|两|三|四|五|六|七|八|九|十|百|"
    r"\d+|[/／]|开)"
)

_QUESTION = re.compile(r"(是什么|什么是|怎么用|如何|为什么|干什么|好用吗)")
_DEFERRED = re.compile(r"(分钟后|小时后|过会儿|过一会)")

_SKIP_REST = re.compile(r"(跳过(这次|本次)?休息|不休息了|结束休息|停止休息)")
_PAUSE = re.compile(r"暂停(番茄钟|专注|倒计时)|(番茄钟|专注)暂停")
_RESUME = re.compile(r"(继续|恢复)(番茄钟|专注|倒计时)")
_CANCEL = re.compile(
    r"(取消|关掉|关闭|停止|结束|退出)(番茄钟|专注|倒计时|番茄)?"
    r"|(番茄钟|专注)(取消|关掉|关闭|停止|结束|退出)"
)
_OPEN = re.compile(r"(打开(番茄钟|番茄)|番茄钟(设置|面板|窗口))")
_NUM = r"[零〇○一二两三四五六七八九十百\d]+"
_START_HINT = re.compile(
    r"(番茄钟|番茄工作法|一轮番茄|个番茄|开番茄|"
    r"开始专注|开启专注|启动专注|"
    r"(开始|开启|启动|开).{0,8}(番茄|专注)|"
    r"专注" + _NUM + r"分钟|" + _NUM + r"分钟专注)"
)

# 工作法别名：(pattern, focus, rest)
_METHOD_PATTERNS = []
for _name, _focus, _rest, _tip in WORK_METHODS:
    _METHOD_PATTERNS.append(
        (re.compile(re.escape(_name.replace(" ", ""))), _focus, _rest)
    )
_METHOD_PATTERNS.extend([
    (re.compile(r"(52\s*/\s*17|五十二\s*/\s*十七|五十二十七)"), 52, 17),
    (re.compile(r"(90分钟周期|九十分钟周期)"), 90, 25),
])


def parse_pomodoro_command(text):
    """解析一句语音。命中返回 dict，否则返回 None。

    ``action`` 为 ``start`` / ``open`` / ``cancel`` / ``pause`` /
    ``resume`` / ``skip_rest``。``start`` 可带 ``minutes``、``rest_minutes``
    （未说则均为 None，沿用面板当前值）。
    """
    if not text or not str(text).strip():
        return None
    raw = _normalize(text)
    if not raw:
        return None
    if _QUESTION.search(raw):
        return None
    if _DEFERRED.search(raw):
        return None

    leftover = _COMMAND_TOKENS.sub("", raw)
    if leftover:
        return None

    if _SKIP_REST.search(raw):
        return _cmd("skip_rest")
    if _PAUSE.search(raw):
        return _cmd("pause")
    if _RESUME.search(raw):
        return _cmd("resume")
    if _CANCEL.search(raw) and re.search(r"(番茄|专注|倒计时)", raw):
        return _cmd("cancel")
    if _OPEN.search(raw) and "开始" not in raw and "开启" not in raw:
        return _cmd("open")

    minutes, rest_minutes = _extract_durations(raw)
    method = _extract_method(raw)
    if method:
        if minutes is None:
            minutes = method[0]
        if rest_minutes is None:
            rest_minutes = method[1]
        return _cmd("start", minutes, rest_minutes)

    if _START_HINT.search(raw) or re.search(r"(开始|开启|启动).{0,8}番茄", raw):
        return _cmd("start", minutes, rest_minutes)

    # 短句「番茄钟」本身视为启动
    if raw in ("番茄钟", "番茄"):
        return _cmd("start")
    return None


def _cmd(action, minutes=None, rest_minutes=None):
    result = {"action": action, "minutes": minutes, "rest_minutes": rest_minutes}
    return result


def _normalize(text):
    text = str(text).strip().translate(_FW_TRANS)
    text = text.replace(" ", "").replace("\u3000", "")
    text = re.sub(r"[,.!?~～'\"“”‘’]+", "", text)
    for src, dst in _STT_ALIASES:
        text = text.replace(src, dst)
    text = _hours_to_minutes(text)
    # 语气词去掉后再匹配，避免「帮我开始一个番茄钟吧」残留干扰
    compact = _FILLER.sub("", text)
    return compact or text


def _hours_to_minutes(text):
    text = re.sub(r"(一个半|1个半)小时", "90分钟", text)
    text = text.replace("半小时", "30分钟")

    def _repl(match):
        n = _parse_number(match.group(1))
        if n is None:
            return match.group(0)
        return "%d分钟" % (n * 60)

    return re.sub(r"([零〇○一二两三四五六七八九十百\d]+)个?小时", _repl, text)


def _extract_method(text):
    for pattern, focus, rest in _METHOD_PATTERNS:
        if pattern.search(text):
            return focus, rest
    return None


def _extract_durations(text):
    """抽取专注 / 休息分钟。同时说出两者时，按出现顺序：先专注后休息。"""
    pairs = []
    for match in re.finditer(
        r"([零〇○一二两三四五六七八九十百\d]+)\s*分钟", text
    ):
        n = _clamp_minutes(_parse_number(match.group(1)), focus=True)
        if n is not None:
            pairs.append((match.start(), n, match.group(0)))
    if not pairs:
        return None, None

    rest_minutes = None
    rest_match = re.search(
        r"休息(?:时长|时间)?([零〇○一二两三四五六七八九十百\d]+)分钟",
        text,
    )
    if not rest_match:
        rest_match = re.search(
            r"([零〇○一二两三四五六七八九十百\d]+)分钟休息",
            text,
        )
    if rest_match:
        rest_minutes = _clamp_minutes(
            _parse_number(rest_match.group(1)), focus=False
        )

    minutes = pairs[0][1]
    if rest_match:
        rest_start, rest_end = rest_match.span()
        focus_pairs = [
            p for p in pairs
            if not (rest_start <= p[0] < rest_end)
        ]
        if focus_pairs:
            minutes = focus_pairs[0][1]
    elif len(pairs) >= 2 and "休息" in text:
        # 「25分钟专注5分钟休息」：第二个数字当休息
        rest_minutes = _clamp_minutes(pairs[1][1], focus=False)
    return minutes, rest_minutes


def _clamp_minutes(value, focus=True):
    if value is None:
        return None
    lo, hi = (
        (POMODORO_MIN_MINUTES, POMODORO_MAX_MINUTES)
        if focus
        else (REST_MIN_MINUTES, REST_MAX_MINUTES)
    )
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _parse_number(token):
    if token is None:
        return None
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    return _parse_cn_int(token)


def _parse_cn_int(token):
    if token == "十":
        return 10
    if "百" in token:
        left, _, rest = token.partition("百")
        hundreds = _digit_or_one(left)
        if hundreds is None:
            return None
        n = hundreds * 100
        if rest.startswith("零"):
            rest = rest[1:]
        if rest:
            ones = _parse_cn_int(rest)
            if ones is None:
                return None
            n += ones
        return n
    if "十" in token:
        left, _, rest = token.partition("十")
        tens = _digit_or_one(left)
        if tens is None:
            return None
        ones = 0
        if rest:
            ones = _single_digit(rest)
            if ones is None:
                return None
        return tens * 10 + ones
    # 「二五」这类漏了「十」的口语 / 识别结果
    if 2 <= len(token) <= 3 and all(ch in _CN_DIGITS for ch in token):
        return int("".join(str(_CN_DIGITS[ch]) for ch in token))
    return _single_digit(token)


def _digit_or_one(token):
    if not token:
        return 1
    return _single_digit(token)


def _single_digit(token):
    if token.isdigit():
        n = int(token)
        return n if 0 <= n <= 9 else None
    if len(token) == 1 and token in _CN_DIGITS:
        return _CN_DIGITS[token]
    return None
