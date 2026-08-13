# -*- coding: utf-8 -*-
"""番茄钟每日完成计数持久化。"""

from datetime import date

from ..config.paths import POMODORO_STATS_PATH
from .json_io import load_json, save_json


class PomodoroStats:
    """按本地日期统计番茄完成数，跨日自动归零。"""

    def __init__(self, path=None):
        self._path = path or POMODORO_STATS_PATH
        raw = load_json(self._path, {})
        if not isinstance(raw, dict):
            raw = {}
        self._date = raw.get("date", "")
        self._count = raw.get("count", 0)
        if not isinstance(self._count, int) or self._count < 0:
            self._count = 0
        self._check_rollover()

    def _today(self):
        return date.today().isoformat()

    def _check_rollover(self):
        if self._date != self._today():
            self._date = self._today()
            self._count = 0

    @property
    def today_count(self):
        self._check_rollover()
        return self._count

    def record_completion(self):
        """记录一次番茄完成，返回更新后的当日计数。"""
        self._check_rollover()
        self._count += 1
        self._save()
        return self._count

    def _save(self):
        save_json(self._path, {"date": self._date, "count": self._count})
