# -*- coding: utf-8 -*-
"""角色状态机：角色视觉状态的唯一决策入口。

原本 ``MaidPet`` 用 ``_is_speaking`` / ``_mouth_open`` 等布尔标志加多个
``QTimer`` 直接 ``setPixmap``。功能一多，睡眠 / 说话 / 进食 / 眨眼就会争抢
同一张图片。这里把「谁来决定当前显示哪张图」收敛到一处：

- 外部功能只调用语义化方法（``begin_speaking`` / ``end_speaking`` …）表达
  「发生了什么」；
- 由状态机根据当前 ``mode`` / ``action`` 决定实际渲染哪张 pixmap，并通过
  ``Scheduler`` 驱动嘴巴动画与眨眼节奏。

Phase 2 只迁移「现有行为」，保证与旧版逐帧一致：

1. 说话时（``SPEAKING``）不眨眼；
2. 关闭嘴巴动画（mute）时，说话期间嘴巴定帧为张嘴图；
3. 每句说完闭嘴、全部说完回到待机；
4. 空闲时以 4~9 秒的随机间隔眨眼，眨眼图停留 160ms。
"""

import random

from PySide6.QtCore import QObject, Signal

from ..config.constants import MOUTH_ANIM_MS
from .character_state import Action, Mode

# Scheduler 任务 id
_TASK_BLINK = "state.blink"
_TASK_BLINK_END = "state.blink_end"
_TASK_MOUTH = "state.mouth"

# 分组：便于将来「勿扰 / 睡眠」一次性关掉待机动画
_GROUP_IDLE_ANIM = "idle_anim"
_GROUP_SPEAK_ANIM = "speak_anim"

# 眨眼节奏（毫秒）。间隔越小，眨眼越频繁。
_BLINK_FIRST_MIN_MS = 3000   # 首次眨眼的最小间隔
_BLINK_FIRST_MAX_MS = 6000   # 首次眨眼的最大间隔
_BLINK_NEXT_MIN_MS = 3000    # 之后每次眨眼的最小间隔
_BLINK_NEXT_MAX_MS = 7000    # 之后每次眨眼的最大间隔
_BLINK_HOLD_MS = 160         # 闭眼图片停留时长


class CharacterStateMachine(QObject):
    """管理角色三态图片的显示。

    参数：
        pixmaps: dict，含 "origin" / "open" / "blink" 三张 QPixmap。
        render: callable(QPixmap)，把 pixmap 渲染到界面上（通常是
            ``char_label.setPixmap``）。
        scheduler: Scheduler 实例，用于驱动嘴巴 / 眨眼定时。
        mute_getter: callable() -> bool，返回当前是否关闭嘴巴动画。
    """

    state_changed = Signal(object, object)  # (old_action, new_action)

    def __init__(self, pixmaps, render, scheduler, mute_getter, parent=None):
        super().__init__(parent)
        self._pix = pixmaps
        self._render = render
        self._scheduler = scheduler
        self._mute_getter = mute_getter

        self.mode = Mode.NORMAL
        self.action = Action.IDLE
        self.overlays = set()
        self._mouth_open = False

    # ---- 生命周期 ----
    def start(self):
        """建立初始画面并启动眨眼节奏（首次间隔 4~8 秒，与旧版一致）。"""
        self._render(self._pix["origin"])
        self._scheduler.schedule_once(
            _TASK_BLINK,
            random.randint(_BLINK_FIRST_MIN_MS, _BLINK_FIRST_MAX_MS),
            self._on_blink_tick,
            group=_GROUP_IDLE_ANIM,
        )

    # ---- 查询 ----
    @property
    def is_speaking(self):
        return self.action == Action.SPEAKING

    # ---- 动作：思考（无视觉变化，仅记录，便于未来扩展） ----
    def begin_thinking(self):
        if self.action == Action.IDLE:
            self._set_action(Action.THINKING)

    # ---- 动作：说话 ----
    def begin_speaking(self):
        """每一句开始逐字时调用。"""
        self._set_action(Action.SPEAKING)
        if self._mute_getter():
            self._scheduler.cancel(_TASK_MOUTH)
            self._render(self._pix["open"])
            return
        self._mouth_open = False
        self._scheduler.schedule_repeating(
            _TASK_MOUTH, MOUTH_ANIM_MS, self._mouth_step, group=_GROUP_SPEAK_ANIM,
        )

    def end_sentence(self):
        """一句说完（句间停顿）：闭嘴，但仍处于说话状态。"""
        self._scheduler.cancel(_TASK_MOUTH)
        self._mouth_open = False
        self._render(self._pix["origin"])

    def end_speaking(self):
        """全部说完并淡出：回到待机。"""
        self._scheduler.cancel(_TASK_MOUTH)
        self._mouth_open = False
        self._set_action(Action.IDLE)
        self._render(self._pix["origin"])

    def _mouth_step(self):
        self._mouth_open = not self._mouth_open
        self._render(self._pix["open"] if self._mouth_open else self._pix["origin"])

    # ---- 动作：眨眼 ----
    def _on_blink_tick(self):
        # 先安排下一次眨眼。
        self._scheduler.schedule_once(
            _TASK_BLINK,
            random.randint(_BLINK_NEXT_MIN_MS, _BLINK_NEXT_MAX_MS),
            self._on_blink_tick,
            group=_GROUP_IDLE_ANIM,
        )
        # 说话时不眨眼。
        if self.is_speaking:
            return
        self._render(self._pix["blink"])
        self._scheduler.schedule_once(
            _TASK_BLINK_END, _BLINK_HOLD_MS, self._on_blink_end,
            group=_GROUP_IDLE_ANIM,
        )

    def _on_blink_end(self):
        if not self.is_speaking:
            self._render(self._pix["origin"])

    # ---- 内部 ----
    def _set_action(self, action):
        if action == self.action:
            return
        old = self.action
        self.action = action
        self.state_changed.emit(old, action)
