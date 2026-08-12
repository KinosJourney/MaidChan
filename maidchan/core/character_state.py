# -*- coding: utf-8 -*-
"""角色状态的正交维度定义。

不要用一个枚举混装所有概念。角色的视觉状态由三个相互独立的维度组合而成：

- ``Mode``（长期模式）：持续较久、会影响其它功能是否生效。当前仅实现
  ``NORMAL``，其余为未来功能（睡眠、专注、游戏、勿扰）预留。
- ``Action``（临时动作）：短暂发生、结束后需要回到上一个合法状态。
- ``overlays``（状态修饰）：叠加在主状态之上、不独占主动作的标记
  （情绪、断网、高负载等），当前以字符串集合形式预留。

Phase 2 只把「现有」的说话 / 眨眼 / 待机行为迁进来，并不改变行为；
其余取值仅作为将来扩展的占位。
"""

from enum import Enum


class Mode(Enum):
    """长期模式（当前仅 NORMAL 生效，其余为未来预留）。"""

    NORMAL = "normal"
    SLEEPING = "sleeping"
    FOCUS = "focus"
    GAME = "game"
    DND = "dnd"


class Action(Enum):
    """临时动作。"""

    IDLE = "idle"
    THINKING = "thinking"
    SPEAKING = "speaking"
    BLINKING = "blinking"
