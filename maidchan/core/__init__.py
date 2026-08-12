# -*- coding: utf-8 -*-
"""核心协调层：角色状态机、统一调度器、通知管理器。

这些模块把原本散落在 ``MaidPet`` 里的定时器、布尔标志和图片切换集中管理，
避免未来每加一个功能都直接争抢角色图片与气泡通道。
"""

from .character_state import Action, Mode
from .notifications import NotificationManager
from .scheduler import Scheduler
from .state_machine import CharacterStateMachine

__all__ = [
    "Mode",
    "Action",
    "Scheduler",
    "CharacterStateMachine",
    "NotificationManager",
]
