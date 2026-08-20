# -*- coding: utf-8 -*-
"""主动陪聊服务。

在主人「未使用番茄钟且处于空闲」时，周期性地让 Maid 主动找主人聊一条
新闻 / 八卦 / 哲学 / 稀奇知识。仿 ``ReminderService``：把触发逻辑与 Qt / 网络
解耦，通过注入回调与可控时钟做确定性测试。

两个周期任务：

- ``proactive.refresh``：低频刷新 RSS 内容（由外部 ``request_refresh`` 执行抓取）。
- ``proactive.check``：更高频地检查是否满足主动聊天的全部门控条件。

门控（全部满足才聊）：功能已启用、不在免打扰时段、番茄钟未运行、
过了启动缓冲期、距上次互动足够久、当前不忙（LLM / 录音 / 气泡）、
距上次主动聊天达到间隔、当日次数未超限。
"""

import random
from datetime import datetime

from ..config.constants import (
    PROACTIVE_CATEGORIES,
    PROACTIVE_CHAT_CHECK_SECONDS,
    PROACTIVE_CHAT_DAILY_LIMIT,
    PROACTIVE_CHAT_ENABLED_DEFAULT,
    PROACTIVE_CHAT_INTERVAL_MINUTES,
    PROACTIVE_CHAT_MIN_IDLE_MINUTES,
    PROACTIVE_CHAT_QUIET_END_HOUR,
    PROACTIVE_CHAT_QUIET_START_HOUR,
    PROACTIVE_CHAT_STARTUP_GRACE_MINUTES,
    CONTENT_FEED_REFRESH_MINUTES,
)

_CHECK_TASK_ID = "proactive.check"
_REFRESH_TASK_ID = "proactive.refresh"
_GROUP = "proactive"


def _in_quiet_hours(hour, start, end):
    """免打扰判断，支持跨午夜。start==end 视为不启用免打扰。"""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # 跨午夜，如 23 点到次日 8 点
    return hour >= start or hour < end


class ProactiveChatService:
    """周期检查空闲状态，并在合适时机触发一次主动聊天。

    Parameters
    ----------
    scheduler : Scheduler
        统一调度器。
    trigger : callable(category, item) -> bool
        真正发起一次主动聊天；成功启动返回 ``True`` 才计入频率 / 每日次数。
    pick_item : callable(category) -> dict | None
        取一条该类别内容；无内容返回 ``None``。
    request_refresh : callable() | None
        触发后台刷新内容源（可选）。
    is_blocked : callable() -> bool
        当前是否忙（对话中 / 录音 / 气泡显示中等）。
    is_pomodoro_running : callable() -> bool
        番茄钟是否进行中（专注或休息）。
    idle_seconds : callable() -> float
        距上次与 Maid 互动的秒数。
    settings_getter : callable(key, default) -> value
        读取配置（每次检查都重新读，改设置即时生效）。
    now_fn : callable() -> datetime
        当前时间，便于测试注入。
    """

    def __init__(self, scheduler, trigger, pick_item, request_refresh,
                 is_blocked, is_pomodoro_running, idle_seconds,
                 settings_getter, now_fn=None,
                 check_interval_seconds=PROACTIVE_CHAT_CHECK_SECONDS,
                 refresh_interval_minutes=CONTENT_FEED_REFRESH_MINUTES):
        self._scheduler = scheduler
        self._trigger = trigger
        self._pick_item = pick_item
        self._request_refresh = request_refresh
        self._is_blocked = is_blocked
        self._is_pomodoro_running = is_pomodoro_running
        self._idle_seconds = idle_seconds
        self._get = settings_getter
        self._now_fn = now_fn or datetime.now
        self._check_interval_ms = int(check_interval_seconds * 1000)
        self._refresh_interval_ms = int(refresh_interval_minutes * 60 * 1000)

        self._started_at = self._now_fn()
        self._last_fired_at = None
        self._count_date = None
        self._daily_count = 0
        self._last_category = None

    # ---- 生命周期 ----
    def start(self):
        self._started_at = self._now_fn()
        if self._request_refresh is not None:
            self._scheduler.schedule_repeating(
                _REFRESH_TASK_ID, self._refresh_interval_ms,
                self._refresh, group=_GROUP,
            )
            self._refresh()
        self._scheduler.schedule_repeating(
            _CHECK_TASK_ID, self._check_interval_ms, self._maybe_chat, group=_GROUP,
        )

    def stop(self):
        self._scheduler.cancel(_CHECK_TASK_ID)
        self._scheduler.cancel(_REFRESH_TASK_ID)

    def _refresh(self):
        if self._request_refresh is not None:
            self._request_refresh()

    # ---- 配置 ----
    def _enabled(self):
        return bool(self._get("proactive_chat_enabled", PROACTIVE_CHAT_ENABLED_DEFAULT))

    def _categories(self):
        cats = self._get("proactive_chat_categories", None)
        if not cats:
            cats = list(PROACTIVE_CATEGORIES)
        return [c for c in cats if c in PROACTIVE_CATEGORIES]

    def _interval_seconds(self):
        return float(self._get(
            "proactive_chat_interval_minutes", PROACTIVE_CHAT_INTERVAL_MINUTES)) * 60

    def _min_idle_seconds(self):
        return float(self._get(
            "proactive_chat_min_idle_minutes", PROACTIVE_CHAT_MIN_IDLE_MINUTES)) * 60

    def _daily_limit(self):
        return int(self._get("proactive_chat_daily_limit", PROACTIVE_CHAT_DAILY_LIMIT))

    def _quiet_hours(self):
        start = int(self._get(
            "proactive_chat_quiet_start", PROACTIVE_CHAT_QUIET_START_HOUR))
        end = int(self._get(
            "proactive_chat_quiet_end", PROACTIVE_CHAT_QUIET_END_HOUR))
        return start, end

    # ---- 触发检查 ----
    def _maybe_chat(self):
        if not self._enabled():
            return
        now = self._now_fn()

        # 启动缓冲：刚打开时不要立刻主动聊，避开问候。
        grace = PROACTIVE_CHAT_STARTUP_GRACE_MINUTES * 60
        if (now - self._started_at).total_seconds() < grace:
            return

        # 免打扰时段
        start, end = self._quiet_hours()
        if _in_quiet_hours(now.hour, start, end):
            return

        # 番茄钟进行中（专注或休息）：完全交给番茄钟，不打扰。
        if self._is_pomodoro_running():
            return

        # 正在对话 / 录音 / 气泡显示中：跳过本次，稍后再看（不排队堆积）。
        if self._is_blocked():
            return

        # 空闲时长不足
        if self._idle_seconds() < self._min_idle_seconds():
            return

        # 距上次主动聊天间隔不足
        if self._last_fired_at is not None:
            if (now - self._last_fired_at).total_seconds() < self._interval_seconds():
                return

        # 每日次数
        self._roll_daily(now)
        if self._daily_count >= self._daily_limit():
            return

        category, item = self._select(now)
        if category is None:
            # 暂时没有可聊的内容：请求刷新，等下次检查。
            self._refresh()
            return

        if self._trigger(category, item):
            self._last_fired_at = now
            self._daily_count += 1
            self._last_category = category

    def _roll_daily(self, now):
        today = now.date()
        if self._count_date != today:
            self._count_date = today
            self._daily_count = 0

    def _select(self, now):
        """选类别 + 取内容。随机且尽量不连续同类；某类别没内容就换一个。"""
        enabled = self._categories()
        if not enabled:
            return None, None
        candidates = [c for c in enabled if c != self._last_category] or list(enabled)
        random.shuffle(candidates)
        # 优先选中的类别，取不到再尝试其它类别，保证有内容才触发。
        ordered = candidates + [c for c in enabled if c not in candidates]
        for category in ordered:
            item = self._pick_item(category)
            if item is not None:
                return category, item
        return None, None
