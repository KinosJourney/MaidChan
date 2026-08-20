# -*- coding: utf-8 -*-
"""主窗口：桌宠本体。"""

import os
import random
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QSize, QEvent
from PySide6.QtGui import (
    QPixmap,
    QPainter,
    QColor,
    QAction,
    QGuiApplication,
    QIcon,
    QPen,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QTextEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QMenu,
    QMessageBox,
)

from ..audio import AudioRecorder, SpeechRecognizeWorker, get_stt_env_config
from ..config.constants import (
    CHARACTER_HEIGHT,
    CONTENT_FEED_SOURCES,
    DEFAULT_PLAYLIST_HOTKEY,
    DEFAULT_PLAYLIST_URL,
    DEFAULT_STT_BASE_URL,
    DEFAULT_STT_LANGUAGE,
    DEFAULT_STT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_VOICE_HOTKEY,
    MAX_CONTEXT_TURNS,
    MAX_MEMORY_INJECT,
    MAX_RECORDING_SECONDS,
    PROACTIVE_CATEGORIES,
    PROACTIVE_CATEGORY_LABELS,
    PROACTIVE_CHAT_ENABLED_DEFAULT,
    PROACTIVE_CHAT_PRIORITY,
    PROACTIVE_LOCAL_POOLS,
    REMINDER_PRIORITY,
)
from ..config.paths import (
    CONTENT_CACHE_PATH,
    DATA_DIR,
    HISTORY_PATH,
    MEMORY_PATH,
    MEMORY_BACKUP_DIR,
    TODOS_PATH,
    IMG_BLINK,
    IMG_OPEN,
    IMG_ORIGIN,
)
from ..core import (
    CharacterStateMachine,
    ChimePlayer,
    NotificationManager,
    ProactiveChatService,
    ReminderService,
    Scheduler,
)
from ..core.content_feed import ContentRefreshWorker
from ..llm.client import ChatWorker
from ..llm.memory_extractor import MemoryExtractWorker
from ..llm.memory_retriever import retrieve_memories_sync
from ..llm.messages import build_chat_messages
from ..llm.todo_extractor import TodoParseWorker
from ..playlist import (
    GlobalHotkey,
    PlaylistWorker,
    hotkey_display,
    qt_key_sequence,
    short_title,
)
from ..storage.content_cache import ContentCache
from ..storage.history import HistoryStore
from ..storage.memory import MemoryStore
from ..storage.profile import Profile
from ..storage.pomodoro_stats import PomodoroStats
from ..storage.settings import Settings
from ..storage.todo import TodoStore, parse_dt
from .dialogs import (
    HelpDialog,
    HistoryDialog,
    MemoryDialog,
    PomodoroDialog,
    ProfileDialog,
    SettingsDialog,
    TodoListDialog,
)
from .image_loader import pixmap_from_image_dewhite
from .macos_window import show_on_all_spaces
from .speech_bubble import SpeechBubble
from .text_utils import split_sentences


def _todo_log(msg):
    """待办诊断日志：同时打印到终端并追加到用户数据目录，方便排查。"""
    line = "%s [待办] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line)
    try:
        with open(os.path.join(DATA_DIR, "todo_debug.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class MaidPet(QWidget):
    def __init__(self):
        super().__init__()

        self.settings = Settings()
        self.profile = Profile()
        self.history = HistoryStore(HISTORY_PATH)
        self.memory = MemoryStore(MEMORY_PATH)
        self.memory.cleanup_expired()
        self.memory.auto_backup(MEMORY_BACKUP_DIR)

        self.system_prompt = self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

        # 记忆系统状态
        self._last_user_msg = ""
        self._current_memories = []
        self._memory_extract_worker = None

        # macOS 上 Qt.Tool 会随应用失去焦点而隐藏，因此使用普通无边框窗口。
        flags = Qt.FramelessWindowHint
        if sys.platform != "darwin":
            flags |= Qt.Tool
        if self.settings.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 载入三态图片
        self.pix_origin = pixmap_from_image_dewhite(IMG_ORIGIN, CHARACTER_HEIGHT)
        self.pix_open = pixmap_from_image_dewhite(IMG_OPEN, CHARACTER_HEIGHT)
        self.pix_blink = pixmap_from_image_dewhite(IMG_BLINK, CHARACTER_HEIGHT)
        if self.pix_origin is None:
            self.pix_origin = self._placeholder()
        if self.pix_open is None:
            self.pix_open = self.pix_origin
        if self.pix_blink is None:
            self.pix_blink = self.pix_origin

        char_w = self.pix_origin.width()

        # 角色图片
        self.char_label = QLabel(self)
        self.char_label.setPixmap(self.pix_origin)
        self.char_label.setFixedSize(self.pix_origin.size())

        # 输入区：可自动增高的多行输入；空内容显示麦克风，有文字显示向上箭头。
        self._input_min_h = 36
        self._input_max_h = 260
        self.input_edit = QTextEdit(self)
        self.input_edit.setAcceptRichText(False)
        self.input_edit.setPlaceholderText("和 Maid 说点什么…（回车发送，Shift+回车换行）")
        self.input_edit.setFixedHeight(self._input_min_h)
        self.input_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_edit.setTabChangesFocus(True)
        # 中文语音结果通常没有空格，必须允许任意位置换行。
        self.input_edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.input_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        self.input_edit.textChanged.connect(self._on_input_changed)
        self.input_edit.installEventFilter(self)
        self.input_edit.setStyleSheet(
            "QTextEdit {"
            "  background: rgba(255,255,255,0.92);"
            "  border: 2px solid #ffb7c5;"
            "  border-radius: 14px;"
            "  padding: 6px 10px;"
            "  color: #3a2b35;"
            "  font-size: 13px;"
            "}"
        )

        self.voice_bar = QLabel(self)
        self.voice_bar.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.voice_bar.setMinimumHeight(self._input_min_h)
        self.voice_bar.hide()
        self.voice_bar.setStyleSheet(
            "QLabel {"
            "  background: rgba(255, 107, 107, 0.14);"
            "  border: 2px solid #ff8a8a;"
            "  border-radius: 14px;"
            "  padding: 6px 12px;"
            "  color: #a33a3a;"
            "  font-size: 13px;"
            "}"
        )

        self.action_btn = QPushButton(self)
        self.action_btn.setFixedSize(34, 34)
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.clicked.connect(self._on_action_clicked)
        self._action_busy = False
        self._mic_available = True

        # 布局
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addWidget(self.char_label, 0, Qt.AlignHCenter)

        self.input_row = QWidget(self)
        input_layout = QHBoxLayout(self.input_row)
        input_layout.setContentsMargins(4, 0, 4, 4)
        input_layout.setSpacing(6)
        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.voice_bar, 1)
        input_layout.addWidget(self.action_btn, 0, Qt.AlignBottom)
        root.addWidget(self.input_row)

        self.input_row.setVisible(self.settings.get("show_input", True))
        self.input_row.setFixedWidth(max(char_w, 300))

        # 统一调度器：集中管理所有定时任务，避免各功能各自造 QTimer。
        self.scheduler = Scheduler(self)

        # 对话气泡
        self.bubble = SpeechBubble()

        # 角色状态机：角色图片的唯一决策入口（嘴巴 / 眨眼 / 待机）。
        self.state = CharacterStateMachine(
            pixmaps={
                "origin": self.pix_origin,
                "open": self.pix_open,
                "blink": self.pix_blink,
            },
            render=self.char_label.setPixmap,
            scheduler=self.scheduler,
            mute_getter=lambda: self.settings.get("mute_anim", False),
            parent=self,
        )

        # 通知管理器：统一说话通道；气泡回调统一转发给状态机。
        self.notifications = NotificationManager(
            bubble=self.bubble,
            split_fn=split_sentences,
            position_cb=self._position_bubble,
            state_machine=self.state,
            parent=self,
        )

        # 空闲检测
        self.last_active = time.time()
        self._idle_greeted = False
        self.scheduler.schedule_repeating("idle", 30000, self._check_idle)

        # 待办提醒：语音 / 手动创建的事项，到点前后用高优先级气泡提醒。
        self.todos = TodoStore(TODOS_PATH)
        self._reminder_chime = ChimePlayer(self)
        self.reminders = ReminderService(
            store=self.todos,
            scheduler=self.scheduler,
            notify=self._remind,
            play_sound=self._reminder_chime.play,
            name_getter=lambda: (
                self.profile.get("call_me") or self.profile.get("nickname") or "主人"
            ),
        )
        self.reminders.start()
        self._todo_parse_worker = None
        self._todo_list_dialog = None

        # 主动陪聊：空闲且未使用番茄钟时，主动聊新闻 / 八卦 / 哲学 / 稀奇知识。
        self._pending_topic = None       # 当前主动话题对应的内容条目 / 优先级
        self._content_worker = None
        self.content_cache = ContentCache(
            CONTENT_CACHE_PATH, local_pools=PROACTIVE_LOCAL_POOLS,
        )
        self.proactive_chat = ProactiveChatService(
            scheduler=self.scheduler,
            trigger=self._trigger_proactive_chat,
            pick_item=self.content_cache.pick,
            request_refresh=self._refresh_content,
            is_blocked=self._chat_busy,
            is_pomodoro_running=lambda: self._pomodoro_dialog.is_running,
            idle_seconds=lambda: time.time() - self.last_active,
            settings_getter=self.settings.get,
        )
        self.proactive_chat.start()

        # 番茄钟：倒计时标签贴在角色旁边
        self._pomodoro_stats = PomodoroStats()
        self._pomo_label = QLabel(self)
        self._pomo_label.setStyleSheet(
            "QLabel {"
            "  background: rgba(255,183,197,0.88);"
            "  color: white; font-size: 14px; font-weight: bold;"
            "  font-family: 'Menlo', 'Consolas', monospace;"
            "  border-radius: 10px; padding: 3px 8px;"
            "}"
        )
        self._pomo_label.setAlignment(Qt.AlignCenter)
        self._pomo_label.hide()
        self._pomodoro_dialog = PomodoroDialog(
            stats=self._pomodoro_stats,
            on_complete=self._pomodoro_done,
            on_tick=self._pomodoro_tick,
            on_state_change=self._pomodoro_state_changed,
            on_rest_done=self._pomodoro_rest_done,
            parent=None,
        )

        # 拖拽
        self._drag_pos = None

        self.worker = None

        # 语音输入
        self._recorder = AudioRecorder(self)
        self._recorder.error.connect(self._on_recorder_error)
        self._stt_worker = None
        self._recording_start = 0.0
        self._mic_available = AudioRecorder.is_available()
        self._refresh_action_btn()

        self._playlist_worker = None
        self._last_playlist_bvid = None
        self._last_playlist_at = 0.0
        self._setup_playlist_shortcut()
        self._setup_voice_shortcut()

        # 恢复窗口位置
        self.adjustSize()
        self._restore_position()

        # 启动待机动画（眨眼），并在打开时问候
        self.state.start()
        self.scheduler.schedule_once("greet", 800, self.greet)

    def showEvent(self, event):
        super().showEvent(event)
        # setWindowFlags() 可能重建原生窗口，因此每次显示时都重新设置。
        show_on_all_spaces(self)

    # ---- 占位图 ----
    def _placeholder(self):
        pm = QPixmap(180, CHARACTER_HEIGHT)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(255, 183, 197))
        p.setPen(Qt.NoPen)
        p.drawEllipse(30, 40, 120, 120)
        p.setPen(QColor(80, 60, 70))
        p.drawText(pm.rect(), Qt.AlignCenter, "Maid")
        p.end()
        return pm

    # ---- 窗口位置 ----
    def _restore_position(self):
        x = self.settings.get("pos_x")
        y = self.settings.get("pos_y")
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if x is None or y is None:
            x = screen.width() - self.width() - 60
            y = screen.height() - self.height() - 40
        # 防止跑到屏幕外
        x = max(0, min(int(x), screen.width() - 50))
        y = max(0, min(int(y), screen.height() - 50))
        self.move(int(x), int(y))

    def _save_position(self):
        self.settings.set("pos_x", self.x())
        self.settings.set("pos_y", self.y())

    def _place_dialog_on_screen(self, dialog):
        """将弹窗放在 Maid 附近，并限制在当前屏幕的可用范围内。"""
        anchor = QPoint(
            self.x() + self.width() // 2,
            self.y() + self.height() // 2,
        )
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()

        x = anchor.x() - dialog.width() // 2
        y = anchor.y() - dialog.height() // 2
        max_x = max(area.left(), area.right() - dialog.width() + 1)
        max_y = max(area.top(), area.bottom() - dialog.height() + 1)
        dialog.move(
            max(area.left(), min(x, max_x)),
            max(area.top(), min(y, max_y)),
        )

    # ---- 气泡定位 ----
    def _position_bubble(self):
        gx = self.x() + self.width() // 2 - self.bubble.width() // 2
        gy = self.y() - self.bubble.height() + 6
        anchor = QPoint(self.x() + self.width() // 2, self.y() + self.height() // 2)
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if gy < area.top():
            gy = self.y() + 6
        gx = max(area.left(), min(gx, area.right() - self.bubble.width() + 1))
        gy = max(area.top(), min(gy, area.bottom() - self.bubble.height() + 1))
        self.bubble.move(gx, gy)

    # ===================== 对话流程 =====================
    def on_send(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if self.worker and self.worker.isRunning():
            self.show_local("稍等，我还在想上一句呢～")
            return
        self.input_edit.clear()
        self._adjust_input_height()
        self.last_active = time.time()
        self._idle_greeted = False

        # 记录用户消息
        self._last_user_msg = text
        self.history.add("user", text)

        # 从长期记忆中检索与当前消息相关的记忆
        self._current_memories = self._retrieve_relevant_memories(text)

        # 构建发给 API 的 messages
        messages = self._build_messages()

        self._set_action_busy(True)
        self.state.begin_thinking()

        self.worker = ChatWorker(messages, self)
        self.worker.finished_ok.connect(self._on_reply)
        self.worker.failed.connect(self._on_reply_failed)
        self.worker.start()

    def _retrieve_relevant_memories(self, user_msg):
        """同步检索相关记忆：用简单关键词匹配，不额外调 API。"""
        words = [w for w in user_msg if len(w.strip()) > 0]
        keywords = []
        for segment in user_msg.replace("，", " ").replace("。", " ").replace(
            "！", " ").replace("？", " ").replace("、", " ").split():
            if len(segment) >= 2:
                keywords.append(segment)
        return retrieve_memories_sync(self.memory, keywords, limit=MAX_MEMORY_INJECT)

    def _build_messages(self):
        return build_chat_messages(
            system_prompt=self.system_prompt,
            profile=self.profile,
            history=self.history,
            memories=self._current_memories,
            max_context_turns=MAX_CONTEXT_TURNS,
        )

    def _on_reply(self, content):
        self._set_action_busy(False)
        self.history.add("maid", content)
        self.say(content)
        # 标记被召回的记忆
        for m in self._current_memories:
            self.memory.mark_recalled(m.get("id"))
        # 后台提取新记忆
        self._extract_memory(self._last_user_msg, content)

    def _on_reply_failed(self, err):
        self._set_action_busy(False)
        self.say(err)

    # ===================== 记忆提取 =====================
    def _extract_memory(self, user_msg, assistant_msg):
        """在后台线程中让模型判断本轮是否值得记忆。"""
        if self._memory_extract_worker and self._memory_extract_worker.isRunning():
            return
        self._memory_extract_worker = MemoryExtractWorker(user_msg, assistant_msg, self)
        self._memory_extract_worker.extracted.connect(self._on_memories_extracted)
        self._memory_extract_worker.failed.connect(self._on_memory_extract_failed)
        self._memory_extract_worker.start()

    def _on_memories_extracted(self, memories):
        """收到提取结果后，存入长期记忆库。"""
        changed = False
        for mem in memories:
            content = mem.get("content", "").strip()
            mem_type = mem.get("type", "profile")
            if not content:
                continue
            # 去重：如果已有相似记忆，更新而非新增
            is_dup, existing = self.memory.deduplicate(content, mem_type)
            if is_dup and existing:
                if len(content) > len(existing.get("content", "")):
                    self.memory.update_content(
                        existing["id"], content, mem.get("tags")
                    )
                    changed = True
            else:
                self.memory.add(
                    memory_type=mem_type,
                    content=content,
                    tags=mem.get("tags", []),
                    importance=mem.get("importance", 0.5),
                    confidence=0.9,
                    source_ids=[self.history.last_message_id or ""],
                )
                changed = True
        # 如果记忆面板正在打开，实时刷新
        if changed and hasattr(self, '_memory_dialog') and self._memory_dialog is not None:
            self._memory_dialog.refresh()

    def _on_memory_extract_failed(self, err):
        pass  # 记忆提取失败不影响正常使用

    # ---- 本地说话（不走 API，不记历史） ----
    def show_local(self, text):
        self.notifications.show(text, record=False)

    def say(self, text, record=False, priority=0):
        # 说话通道统一走通知管理器；嘴巴 / 眨眼由状态机决定。
        self.notifications.show(text, record=record, priority=priority)

    def _chat_busy(self):
        """是否正忙（对话中 / 录音 / 识别中 / 气泡显示中），用于主动陪聊门控。"""
        return bool(
            (self.worker is not None and self.worker.isRunning())
            or self.notifications.is_busy()
            or self._action_busy
            or self._recorder.is_recording
            or (self._stt_worker is not None and self._stt_worker.isRunning())
        )

    # ===================== 空闲 / 问候 =====================
    def greet(self):
        """启动时的简单本地问候（不走 API）。"""
        hour = datetime.now().hour
        name = self.profile.get("call_me") or self.profile.get("nickname") or "主人"
        if 5 <= hour < 11:
            msg = "早上好，%s！新的一天也要元气满满哦～" % name
        elif 11 <= hour < 14:
            msg = "%s，该吃午饭啦，别饿着自己。" % name
        elif 14 <= hour < 18:
            msg = "下午好，%s，工作之余记得休息一下眼睛～" % name
        elif 18 <= hour < 23:
            msg = "晚上好，%s，今天辛苦了。" % name
        else:
            msg = "这么晚还不睡吗，%s？早点休息对身体好哦。" % name
        self.show_local(msg)

    def start_new_topic(self):
        """菜单「和我打个招呼」：让 Maid 主动开启一个随意的新话题。"""
        if self.worker and self.worker.isRunning():
            self.show_local("稍等，我还在想上一句呢～")
            return
        self._begin_topic(category=None, item=None, priority=0)

    def _trigger_proactive_chat(self, category, item):
        """主动陪聊服务的回调：就一条内容找主人聊。成功启动返回 True。"""
        if self.worker and self.worker.isRunning():
            return False
        return self._begin_topic(category=category, item=item,
                                 priority=PROACTIVE_CHAT_PRIORITY)

    def _begin_topic(self, category, item, priority):
        """构建主动话题的 messages 并发起 LLM 请求。"""
        self.last_active = time.time()
        # 主动聊天已接管这一轮空闲陪伴，避免本地 idle 提示再叠加。
        self._idle_greeted = True

        recent_memories = self.memory.get_recent_important(limit=MAX_MEMORY_INJECT)
        messages = build_chat_messages(
            system_prompt=self.system_prompt,
            profile=self.profile,
            history=self.history,
            memories=recent_memories,
            max_context_turns=MAX_CONTEXT_TURNS,
        )
        messages.append({
            "role": "user",
            "content": self._topic_instruction(category, item),
        })

        if item is not None:
            self.content_cache.mark_used(item)
        self._pending_topic = {"item": item, "priority": priority}

        self._set_action_busy(True)
        self.state.begin_thinking()

        self.worker = ChatWorker(messages, self)
        self.worker.finished_ok.connect(self._on_topic_reply)
        self.worker.failed.connect(self._on_topic_failed)
        self.worker.start()
        return True

    def _topic_instruction(self, category, item):
        """根据类别和内容条目，拼出给模型的主动开话题系统指令。"""
        name = self.profile.get("call_me") or self.profile.get("nickname") or "主人"
        hour = datetime.now().hour

        if item is not None:
            label = PROACTIVE_CATEGORY_LABELS.get(category, "话题")
            source = item.get("source") or ""
            title = item.get("title") or ""
            summary = item.get("summary") or ""
            return (
                "[系统指令，非用户发言] 下面是一条「%s」素材，请你用 Maid 的口吻，"
                "自然地把它分享给%s并简短点评（1~3 句，像朋友刷手机时随口聊起）。"
                "只能依据我给出的标题和摘要来说，不要编造我没有提供的细节、数字或结论，"
                "不确定就用「好像」「据说」带过。最后自然地抛出一个问题，邀请%s继续聊。"
                "不要复述「以下是」之类的话，也不要标注来源。\n"
                "【%s·来源：%s】\n标题：%s\n摘要：%s"
            ) % (label, name, name, label, source, title, summary)

        # 无具体内容：回退到随意闲聊（与旧行为一致）。
        return (
            "[系统指令，非用户发言] 现在请你主动开启一个新话题和%s聊天。"
            "可以根据你对%s的了解（记忆中的信息）、当前时间（%d 点）、"
            "或是你自己感兴趣的话题来发起对话。"
            "要自然随意，就像朋友突然想找人聊天一样，"
            "不要说「有什么可以帮你的」之类的客服话术，"
            "也不要重复之前说过的话。"
        ) % (name, name, hour)

    def _on_topic_reply(self, content):
        self._set_action_busy(False)
        pending = self._pending_topic or {}
        self._pending_topic = None
        item = pending.get("item")
        priority = pending.get("priority", 0)

        display = content
        record = content
        if item and item.get("source"):
            display = "%s\n（via %s）" % (content, item["source"])
            link = item.get("link") or ""
            record = "%s\n[来源] %s %s" % (content, item["source"], link.strip())
        self.history.add("maid", record)
        self.say(display, priority=priority)

    def _on_topic_failed(self, err):
        self._set_action_busy(False)
        self._pending_topic = None
        self.greet()

    # ---- 主动陪聊内容源 ----
    def _refresh_content(self):
        """后台抓取 RSS 内容源，抓完写入缓存。"""
        if self._content_worker is not None and self._content_worker.isRunning():
            return
        self._content_worker = ContentRefreshWorker(CONTENT_FEED_SOURCES, parent=self)
        self._content_worker.finished_ok.connect(self._on_content_refreshed)
        self._content_worker.start()

    def _on_content_refreshed(self, category_items):
        self.content_cache.update(category_items)

    def _test_proactive_chat(self, categories=None):
        """设置面板「立即试聊」按钮：不受空闲 / 间隔 / 番茄钟限制，直接试发一条。"""
        if self.worker and self.worker.isRunning():
            self.show_local("稍等，我还在想上一句呢～")
            return
        cats = [c for c in (categories or []) if c in PROACTIVE_CATEGORIES]
        if not cats:
            cats = list(PROACTIVE_CATEGORIES)
        order = list(cats)
        random.shuffle(order)
        for category in order:
            item = self.content_cache.pick(category)
            if item is not None:
                self._trigger_proactive_chat(category, item)
                return
        # 选的类别暂时都没有内容（如新闻 / 八卦还没抓到）：先去抓一批。
        self._refresh_content()
        self.show_local("内容还在路上，我先去抓一批新闻，稍等一下再点一次试试～")

    def _check_idle(self):
        # 主动陪聊已开启时，由它负责空闲陪伴，这里不再叠加本地提示。
        if self.settings.get("proactive_chat_enabled", PROACTIVE_CHAT_ENABLED_DEFAULT):
            return
        idle = time.time() - self.last_active
        if idle > 600 and not self._idle_greeted and not self.state.is_speaking:
            self._idle_greeted = True
            name = self.profile.get("call_me") or "主人"
            tips = [
                "%s，我在这里陪着你哦～" % name,
                "有点想你了，%s。" % name,
                "记得多喝水，%s。" % name,
            ]
            self.show_local(random.choice(tips))

    # ===================== 输入区操作按钮 / 语音输入 =====================
    def _setup_voice_shortcut(self):
        self._global_voice_hotkey = GlobalHotkey(
            DEFAULT_VOICE_HOTKEY, widget=self, parent=self
        )
        self._global_voice_hotkey.pressed.connect(self._on_push_to_talk_pressed)
        self._global_voice_hotkey.released.connect(self._on_push_to_talk_released)

    def _on_push_to_talk_pressed(self):
        if self._action_busy or self._recorder.is_recording:
            return
        if self._stt_worker and self._stt_worker.isRunning():
            return
        if self._input_text():
            self.show_local("输入框里还有内容，请先发送后再使用语音快捷键～")
            return
        self._start_recording()

    def _on_push_to_talk_released(self):
        if self._recorder.is_recording:
            self._stop_recording()

    def eventFilter(self, obj, event):
        if obj is self.input_edit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self.on_send()
                return True
        return super().eventFilter(obj, event)

    def _on_input_changed(self):
        self._adjust_input_height()
        self._refresh_action_btn()

    def _adjust_input_height(self):
        """按内容自动增高输入框，超出上限后出现滚动条。"""
        edit = self.input_edit
        doc = edit.document()

        avail_w = edit.viewport().width()
        if avail_w < 40:
            avail_w = max(40, self.input_row.width() - self.action_btn.width() - 40)
        avail_w = max(40, avail_w)
        doc.setTextWidth(avail_w)

        # QTextEdit 会完整排版文档，size().height() 即内容高度
        doc_h = doc.size().height()
        chrome = edit.height() - edit.viewport().height()
        if chrome < 12:
            chrome = 20  # 边框 + padding 兜底
        target = int(doc_h + chrome + 4)

        # 再用字数估算兜底，避免偶发排版高度偏小
        text = edit.toPlainText()
        if text:
            fm = edit.fontMetrics()
            char_w = max(1, fm.horizontalAdvance("汉"))
            chars_per_line = max(1, avail_w // char_w)
            est_lines = 0
            for paragraph in text.split("\n"):
                if paragraph == "":
                    est_lines += 1
                else:
                    est_lines += max(1, (len(paragraph) + chars_per_line - 1) // chars_per_line)
            est_h = int(est_lines * fm.lineSpacing() + chrome)
            target = max(target, est_h)

        target = max(self._input_min_h, min(target, self._input_max_h))
        if edit.height() != target:
            edit.setFixedHeight(target)
            edit.updateGeometry()
            self.input_row.adjustSize()
            self.adjustSize()
        if target >= self._input_max_h:
            edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def _input_text(self):
        return self.input_edit.toPlainText().strip()

    def _on_action_clicked(self):
        if self._action_busy:
            return
        if self._recorder.is_recording:
            self._stop_recording()
            return
        if self._stt_worker and self._stt_worker.isRunning():
            return
        if self._input_text():
            self.on_send()
            return
        self._start_recording()

    def _set_action_busy(self, busy):
        self._action_busy = busy
        self._refresh_action_btn()

    def _refresh_action_btn(self):
        """根据当前状态切换圆形按钮：麦克风 / 向上箭头 / 停止 / 忙碌。"""
        recording = self._recorder.is_recording
        recognizing = bool(self._stt_worker and self._stt_worker.isRunning())
        has_text = bool(self._input_text())

        if self._action_busy:
            self._set_action_icon("busy", "#ffffff")
            self.action_btn.setEnabled(False)
            self.action_btn.setToolTip("思考中…")
            self.action_btn.setStyleSheet(self._action_style("#e0c3ca"))
            return

        if recording:
            self._set_action_icon("stop", "#ffffff")
            self.action_btn.setEnabled(True)
            self.action_btn.setToolTip("点击停止录音")
            self.action_btn.setStyleSheet(self._action_style("#ff6b6b", hover="#ff4a4a"))
            return

        if recognizing:
            self._set_action_icon("busy", "#ffffff")
            self.action_btn.setEnabled(False)
            self.action_btn.setToolTip("正在识别语音…")
            self.action_btn.setStyleSheet(self._action_style("#e0c3ca"))
            return

        if has_text:
            self._set_action_icon("send", "#ffffff")
            self.action_btn.setEnabled(True)
            self.action_btn.setToolTip("发送")
            self.action_btn.setStyleSheet(self._action_style("#ffb7c5", hover="#ff9db0"))
            return

        mic_ok = getattr(self, "_mic_available", True)
        self.action_btn.setEnabled(mic_ok)
        if mic_ok:
            self._set_action_icon("mic", "#ffffff")
            self.action_btn.setToolTip("点击开始语音输入，再次点击停止")
            self.action_btn.setStyleSheet(self._action_style("#ffb7c5", hover="#ff9db0"))
        else:
            self._set_action_icon("mic", "#b0a4a8")
            self.action_btn.setToolTip("语音输入不可用（缺少麦克风或 QtMultimedia）")
            self.action_btn.setStyleSheet(self._action_style("#e8e0e4"))

    def _set_action_icon(self, kind, color):
        self.action_btn.setText("")
        self.action_btn.setIcon(self._make_action_icon(kind, QColor(color)))
        side = max(16, int(self.action_btn.width() * 0.55))
        self.action_btn.setIconSize(QSize(side, side))

    @staticmethod
    def _make_action_icon(kind, color):
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(color, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(color)

        if kind == "send":
            # 向上箭头
            p.drawLine(32, 50, 32, 16)
            p.drawLine(32, 16, 18, 30)
            p.drawLine(32, 16, 46, 30)
        elif kind == "mic":
            # 实心胶囊麦克风 + 底座弧线
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(24, 10, 16, 28, 8, 8)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(16, 24, 32, 26, 0, -180 * 16)
            p.drawLine(32, 50, 32, 56)
            p.drawLine(22, 56, 42, 56)
        elif kind == "stop":
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(20, 20, 24, 24, 4, 4)
        else:  # busy
            p.setPen(Qt.NoPen)
            for i, x in enumerate((18, 32, 46)):
                p.setOpacity(0.45 + i * 0.25)
                p.drawEllipse(x - 4, 28, 8, 8)
        p.end()
        return QIcon(pm)

    @staticmethod
    def _action_style(bg, hover=None):
        hover = hover or bg
        return (
            "QPushButton {"
            "  background: %s; color: white; border: none;"
            "  border-radius: 17px; padding: 0px;"
            "}"
            "QPushButton:hover { background: %s; }"
            "QPushButton:disabled { background: #e8e0e4; }"
        ) % (bg, hover)

    def _show_voice_bar(self, text="正在听…"):
        self.input_edit.hide()
        self.voice_bar.setText(text)
        self.voice_bar.show()

    def _hide_voice_bar(self):
        self.voice_bar.hide()
        self.input_edit.show()

    def _start_recording(self):
        if not getattr(self, "_mic_available", True):
            return
        if self._stt_worker and self._stt_worker.isRunning():
            self.show_local("语音正在识别中，请稍等～")
            return
        if self._recorder.start():
            self._recording_start = time.time()
            self._audio_levels = []
            self._show_voice_bar("正在听…  0s")
            self._refresh_action_btn()
            self.scheduler.schedule_repeating(
                "mic_display", 150, self._update_mic_display,
            )
            self.scheduler.schedule_once(
                "mic_timeout", MAX_RECORDING_SECONDS * 1000,
                self._auto_stop_recording,
            )

    def _update_mic_display(self):
        elapsed = int(time.time() - self._recording_start)
        peak = self._recorder.peak_level()
        self._audio_levels.append(peak)
        if len(self._audio_levels) > 10:
            self._audio_levels = self._audio_levels[-10:]
        bars = "".join(self._level_char(lv) for lv in self._audio_levels)
        self.voice_bar.setText("正在听…  %ds  %s" % (elapsed, bars))

    @staticmethod
    def _level_char(level):
        chars = "▁▂▃▄▅▆▇█"
        idx = min(int(level * len(chars)), len(chars) - 1)
        return chars[idx]

    def _stop_recording(self):
        self.scheduler.cancel("mic_timeout")
        self.scheduler.cancel("mic_display")
        duration = time.time() - self._recording_start
        wav_data = self._recorder.stop()

        if duration < 0.5 or len(wav_data) < 5000:
            self.show_local("录音太短了，请说长一点～")
            self._reset_voice_ui()
            return

        self._save_debug_wav(wav_data)
        self._send_to_stt(wav_data)

    def _auto_stop_recording(self):
        if self._recorder.is_recording:
            self.show_local("录音已达最大时长，自动停止。")
            self._stop_recording()

    def _save_debug_wav(self, wav_data):
        try:
            path = os.path.join(DATA_DIR, "last_recording.wav")
            with open(path, "wb") as f:
                f.write(wav_data)
        except OSError:
            pass

    def _send_to_stt(self, wav_data):
        self._show_voice_bar("识别中…")

        env_key, env_url, env_model = get_stt_env_config()
        base_url = self.settings.get("stt_base_url", "") or env_url or DEFAULT_STT_BASE_URL
        api_key = self.settings.get("stt_api_key", "") or env_key
        model = self.settings.get("stt_model", "") or env_model or DEFAULT_STT_MODEL
        language = self.settings.get("stt_language", DEFAULT_STT_LANGUAGE)

        self._stt_worker = SpeechRecognizeWorker(
            wav_data, base_url, api_key, model, language, self,
        )
        self._stt_worker.finished_ok.connect(self._on_stt_result)
        self._stt_worker.failed.connect(self._on_stt_failed)
        self._stt_worker.start()
        self._refresh_action_btn()

    def _on_stt_result(self, text):
        self._hide_voice_bar()
        self.input_edit.setPlainText(text)
        self.input_edit.moveCursor(QTextCursor.End)
        # 布局稳定后再算一次高度，避免刚显示时宽度不准
        self._adjust_input_height()
        self.scheduler.schedule_once("input_height", 50, self._adjust_input_height)
        self._reset_voice_ui()
        # 语音识别成功后立即发送；待办识别仅作为独立的后台附加处理。
        self.on_send()
        self._maybe_parse_todo(text)

    def _on_stt_failed(self, err):
        debug_path = os.path.join(DATA_DIR, "last_recording.wav")
        if os.path.isfile(debug_path):
            size_kb = os.path.getsize(debug_path) // 1024
            self.show_local("%s（录音 %dKB 已保存到 MaidChan 目录）" % (err, size_kb))
        else:
            self.show_local(err)
        self._reset_voice_ui()

    def _on_recorder_error(self, err):
        self.show_local(err)
        self._reset_voice_ui()

    def _reset_voice_ui(self):
        self._hide_voice_bar()
        self._refresh_action_btn()

    # ===================== 待办提醒 =====================
    def _remind(self, text, priority=REMINDER_PRIORITY):
        """提醒服务的通知回调：走高优先级气泡，不被普通闲聊顶掉。"""
        self.notifications.show(text, priority=priority)

    def _maybe_parse_todo(self, text):
        """在后台判断语音是否为待办，不阻塞或控制聊天消息发送。"""
        if not text.strip():
            return
        _todo_log("开始解析语音文本：%s" % text)
        if self._todo_parse_worker and self._todo_parse_worker.isRunning():
            _todo_log("上一次解析仍在进行，跳过本次待办解析")
            return
        self._todo_parse_worker = TodoParseWorker(text, datetime.now(), self)
        self._todo_parse_worker.parsed.connect(self._on_todo_parsed)
        self._todo_parse_worker.failed.connect(self._on_todo_parse_failed)
        self._todo_parse_worker.start()

    def _on_todo_parsed(self, result):
        _todo_log("解析结果：%r" % (result,))
        if not result.get("is_todo"):
            return
        content = result.get("content", "").strip()
        due_dt = parse_dt(result.get("due_at"))
        if not content or due_dt is None:
            _todo_log("内容或时间无效，未创建")
            return
        item = self.todos.add(content, due_dt, source="voice")
        if item is None:
            _todo_log("todos.add 返回 None，创建失败")
            return
        _todo_log("已创建待办 id=%s content=%s due=%s"
                  % (item.get("id"), content, item.get("due_at")))
        self.reminders.refresh()
        if self._todo_list_dialog is not None:
            self._todo_list_dialog.refresh()
        when = due_dt.strftime("%m月%d日 %H:%M")
        self.show_local(
            "好的，已加入待办：「%s」，我会在 %s 提前提醒你～（右键「待办事项」可修改或删除）"
            % (content, when)
        )

    def _on_todo_parse_failed(self, err):
        _todo_log("解析失败：%s" % err)

    def open_todos(self):
        if self._todo_list_dialog is not None:
            self._todo_list_dialog.refresh()
            self._place_dialog_on_screen(self._todo_list_dialog)
            self._todo_list_dialog.raise_()
            self._todo_list_dialog.activateWindow()
            return
        self._todo_list_dialog = TodoListDialog(
            self.todos, on_changed=self.reminders.refresh, parent=None
        )
        self._todo_list_dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._todo_list_dialog.destroyed.connect(
            lambda: setattr(self, "_todo_list_dialog", None)
        )
        self._place_dialog_on_screen(self._todo_list_dialog)
        self._todo_list_dialog.show()

    # ===================== 番茄钟 =====================
    def open_pomodoro(self):
        self._place_dialog_on_screen(self._pomodoro_dialog)
        self._pomodoro_dialog.show_and_raise()

    def _pomodoro_tick(self, time_text):
        self._pomo_label.setText(time_text)
        self._position_pomo_label()

    def _pomodoro_state_changed(self, running):
        if running:
            self._pomo_label.show()
        else:
            self._pomo_label.hide()

    def _position_pomo_label(self):
        self._pomo_label.adjustSize()
        cx = self.char_label.x() + self.char_label.width() - self._pomo_label.width() - 2
        cy = self.char_label.y() + 30
        self._pomo_label.move(cx, cy)

    def _pomodoro_done(self, count):
        name = self.profile.get("call_me") or "主人"
        self.show_local(
            "时间到啦，%s！休息一下吧～今天已经完成 %d 个番茄了，真棒！" % (name, count)
        )

    def _pomodoro_rest_done(self):
        name = self.profile.get("call_me") or "主人"
        self.show_local("休息结束啦，%s！我们继续加油吧～" % name)

    # ===================== 合集随机播放 =====================
    def _setup_playlist_shortcut(self):
        seq = qt_key_sequence(DEFAULT_PLAYLIST_HOTKEY)
        self.act_playlist = QAction(
            "随机播放合集（%s）" % hotkey_display(DEFAULT_PLAYLIST_HOTKEY), self
        )
        self.act_playlist.setShortcut(seq)
        self.act_playlist.setShortcutContext(Qt.ApplicationShortcut)
        self.act_playlist.setShortcutVisibleInContextMenu(False)
        self.act_playlist.triggered.connect(self.play_random_from_playlist)
        self.addAction(self.act_playlist)

        self._global_hotkey = GlobalHotkey(
            DEFAULT_PLAYLIST_HOTKEY, widget=self, parent=self
        )
        self._global_hotkey.activated.connect(self.play_random_from_playlist)

    def play_random_from_playlist(self):
        if self._playlist_worker is not None and self._playlist_worker.isRunning():
            return
        now = time.time()
        if now - self._last_playlist_at < 1.0:
            return
        self._last_playlist_at = now

        url = self.settings.get("playlist_url", DEFAULT_PLAYLIST_URL)
        self.show_local("我去合集里抽一条～")
        self._playlist_worker = PlaylistWorker(
            url, exclude_bvid=self._last_playlist_bvid, parent=self
        )
        self._playlist_worker.finished_ok.connect(self._on_playlist_ready)
        self._playlist_worker.failed.connect(self._on_playlist_failed)
        self._playlist_worker.start()

    def _on_playlist_ready(self, video):
        url = video.get("url")
        if not url:
            self._on_playlist_failed("没有拿到视频地址。")
            return
        self._last_playlist_bvid = video.get("bvid")
        try:
            webbrowser.open(url, new=2)
        except Exception:
            self.show_local("浏览器打不开呢，链接是：%s" % url)
            return
        title = short_title(video.get("title") or "")
        self.show_local("给你抽到了《%s》，一起看吧～" % title)

    def _on_playlist_failed(self, err):
        fallback = self.settings.get("playlist_url", DEFAULT_PLAYLIST_URL)
        try:
            webbrowser.open(fallback, new=2)
        except Exception:
            pass
        self.show_local("%s。先帮你打开合集页面啦～" % err.rstrip("。～ "))

    # ===================== 右键菜单 =====================
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #fffdfa; border: 1px solid #ffb7c5; padding: 4px; }"
            "QMenu::item { padding: 6px 24px; border-radius: 6px; }"
            "QMenu::item:selected { background: #ffe0e6; }"
        )

        act_history = QAction("历史记录…", self)
        act_history.triggered.connect(self.open_history)
        menu.addAction(act_history)

        act_memory = QAction("长期记忆（%d 条）…" % self.memory.enabled_count, self)
        act_memory.triggered.connect(self.open_memory)
        menu.addAction(act_memory)

        act_settings = QAction("设置 · 人设…", self)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        act_profile = QAction("御主档案…", self)
        act_profile.triggered.connect(self.open_profile)
        menu.addAction(act_profile)

        act_help = QAction("帮助 / 说明…", self)
        act_help.triggered.connect(self.open_help)
        menu.addAction(act_help)

        menu.addSeparator()

        act_greet = QAction("和我打个招呼", self)
        act_greet.triggered.connect(self.start_new_topic)
        menu.addAction(act_greet)

        pomo_text = "番茄钟（进行中…）" if self._pomodoro_dialog.is_running else "番茄钟…"
        act_pomo = QAction(pomo_text, self)
        act_pomo.triggered.connect(self.open_pomodoro)
        menu.addAction(act_pomo)

        pending = self.todos.pending_count
        todo_text = ("待办事项（%d）…" % pending) if pending else "待办事项…"
        act_todo = QAction(todo_text, self)
        act_todo.triggered.connect(self.open_todos)
        menu.addAction(act_todo)

        menu.addAction(self.act_playlist)

        menu.addSeparator()

        act_top = QAction("取消置顶" if self.settings.get("always_on_top") else "窗口置顶", self)
        act_top.triggered.connect(self.toggle_on_top)
        menu.addAction(act_top)

        act_input = QAction("隐藏输入框" if self.input_row.isVisible() else "显示输入框", self)
        act_input.triggered.connect(self.toggle_input)
        menu.addAction(act_input)

        act_mute = QAction("关闭嘴巴动画" if not self.settings.get("mute_anim") else "开启嘴巴动画", self)
        act_mute.triggered.connect(self.toggle_mute)
        menu.addAction(act_mute)

        if sys.platform == "darwin":
            autostart_on = self._is_autostart_enabled()
            act_autostart = QAction(
                "关闭开机启动" if autostart_on else "开启开机启动", self
            )
            act_autostart.triggered.connect(self.toggle_autostart)
            menu.addAction(act_autostart)

        act_clear = QAction("清空聊天记忆", self)
        act_clear.triggered.connect(self.clear_memory)
        menu.addAction(act_clear)

        menu.addSeparator()

        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        menu.exec(event.globalPos())

    def open_history(self):
        dlg = HistoryDialog(self.history, on_changed=lambda: None, parent=self)
        self._place_dialog_on_screen(dlg)
        dlg.exec()

    def open_memory(self):
        if hasattr(self, '_memory_dialog') and self._memory_dialog is not None:
            self._memory_dialog.refresh()
            self._place_dialog_on_screen(self._memory_dialog)
            self._memory_dialog.raise_()
            self._memory_dialog.activateWindow()
            return
        self._memory_dialog = MemoryDialog(self.memory, parent=None)
        self._memory_dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._memory_dialog.destroyed.connect(lambda: setattr(self, '_memory_dialog', None))
        self._place_dialog_on_screen(self._memory_dialog)
        self._memory_dialog.show()

    def open_settings(self):
        dlg = SettingsDialog(
            self.settings,
            on_saved=self._on_settings_saved,
            on_test_proactive=self._test_proactive_chat,
            parent=self,
        )
        self._place_dialog_on_screen(dlg)
        dlg.exec()

    def _on_settings_saved(self, prompt_changed=True):
        if prompt_changed:
            # 立即更新内存 prompt，并重置短期上下文（清空发给 API 的历史）
            self.system_prompt = self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
            self.history.clear()
            self.show_local("新的人设我记住啦～之前的对话上下文已经重置。")
        else:
            self.show_local("设置已保存。下次随机播放会用新的合集哦～")

    def open_profile(self):
        dlg = ProfileDialog(self.profile, on_saved=self._on_profile_saved, parent=self)
        self._place_dialog_on_screen(dlg)
        dlg.exec()

    def _on_profile_saved(self):
        name = self.profile.get("call_me") or self.profile.get("nickname") or "主人"
        self.show_local("档案已保存，%s，我会好好记住你的～" % name)

    def open_help(self):
        dlg = HelpDialog(parent=self)
        self._place_dialog_on_screen(dlg)
        dlg.exec()

    def toggle_on_top(self):
        new_val = not self.settings.get("always_on_top", True)
        self.settings.set("always_on_top", new_val)
        flags = Qt.FramelessWindowHint
        if sys.platform != "darwin":
            flags |= Qt.Tool
        if new_val:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def toggle_input(self):
        vis = not self.input_row.isVisible()
        self.input_row.setVisible(vis)
        self.settings.set("show_input", vis)
        self.adjustSize()

    def toggle_mute(self):
        self.settings.set("mute_anim", not self.settings.get("mute_anim", False))

    # ===================== 开机启动（macOS LaunchAgent） =====================

    _LAUNCHAGENT_LABEL = "com.maidchan.desktop-pet"

    @property
    def _plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{self._LAUNCHAGENT_LABEL}.plist"

    @property
    def _project_dir(self) -> Path:
        """项目根目录（oc.py 所在目录）。"""
        return Path(__file__).resolve().parent.parent.parent

    def _is_autostart_enabled(self) -> bool:
        return self._plist_path.is_file()

    def toggle_autostart(self):
        if self._is_autostart_enabled():
            self._disable_autostart()
            self.show_local("开机启动已关闭～下次登录不会自动启动了。")
        else:
            self._enable_autostart()
            self.show_local("开机启动已开启！下次登录 Mac 会自动启动哦～")

    def _enable_autostart(self):
        project = self._project_dir
        python_bin = project / ".venv" / "bin" / "python"
        script = project / "oc.py"
        log_file = project / "maidchan-launch.log"

        plist_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self._LAUNCHAGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>{script}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONIOENCODING</key>
        <string>utf-8</string>
    </dict>
    <key>StandardOutPath</key>
    <string>{log_file}</string>
    <key>StandardErrorPath</key>
    <string>{log_file}</string>
</dict>
</plist>
"""
        self._plist_path.parent.mkdir(parents=True, exist_ok=True)
        self._plist_path.write_text(plist_content, encoding="utf-8")

    def _disable_autostart(self):
        if self._plist_path.is_file():
            subprocess.run(["launchctl", "unload", str(self._plist_path)],
                           capture_output=True)
            self._plist_path.unlink(missing_ok=True)

    def clear_memory(self):
        ret = QMessageBox.question(
            self, "确认",
            "确定要清空全部记忆吗？这将清除聊天历史和长期记忆，角色会完全忘记你。"
        )
        if ret == QMessageBox.Yes:
            self.history.clear()
            self.memory.clear()
            self.show_local("好的，我已经把所有关于你的记忆都忘掉了～")

    def quit_app(self):
        self._save_position()
        self._teardown()
        QApplication.quit()

    def _teardown(self):
        """统一清理：停止全部定时任务、等待后台请求结束、关闭气泡。"""
        self.scheduler.shutdown()
        if self._recorder.is_recording:
            self._recorder.cancel()
        if self._global_hotkey is not None:
            self._global_hotkey.unregister()
        if self._global_voice_hotkey is not None:
            self._global_voice_hotkey.unregister()
        if self._playlist_worker is not None and self._playlist_worker.isRunning():
            self._playlist_worker.wait(2000)
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        if self._stt_worker is not None and self._stt_worker.isRunning():
            self._stt_worker.wait(3000)
        if self._todo_parse_worker is not None and self._todo_parse_worker.isRunning():
            self._todo_parse_worker.wait(3000)
        if self._content_worker is not None and self._content_worker.isRunning():
            self._content_worker.wait(3000)
        if self._todo_list_dialog is not None:
            self._todo_list_dialog.close()
        self._pomodoro_dialog.close()
        self.bubble.close()

    # ===================== 拖拽移动 =====================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.last_active = time.time()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            if self.bubble.isVisible():
                self._position_bubble()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            self._drag_pos = None
            self._save_position()

    def closeEvent(self, event):
        self._save_position()
        self._teardown()
        event.accept()
