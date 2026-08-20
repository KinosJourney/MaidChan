# -*- coding: utf-8 -*-
"""右键菜单弹出的各类对话框。"""

from .help_dialog import HelpDialog
from .history_dialog import HistoryDialog
from .memory_dialog import MemoryDialog
from .pomodoro_dialog import PomodoroDialog
from .profile_dialog import ProfileDialog
from .settings_dialog import SettingsDialog
from .todo_dialog import TodoEditDialog, TodoListDialog

__all__ = [
    "HistoryDialog",
    "MemoryDialog",
    "PomodoroDialog",
    "SettingsDialog",
    "ProfileDialog",
    "HelpDialog",
    "TodoEditDialog",
    "TodoListDialog",
]
