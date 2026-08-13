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

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import (
    QPixmap,
    QPainter,
    QColor,
    QAction,
    QGuiApplication,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QMenu,
    QMessageBox,
)

from ..config.constants import (
    CHARACTER_HEIGHT,
    DEFAULT_PLAYLIST_HOTKEY,
    DEFAULT_PLAYLIST_URL,
    DEFAULT_SYSTEM_PROMPT,
    MAX_CONTEXT_TURNS,
)
from ..config.paths import HISTORY_PATH, IMG_BLINK, IMG_OPEN, IMG_ORIGIN
from ..core import CharacterStateMachine, NotificationManager, Scheduler
from ..llm.client import ChatWorker
from ..llm.messages import build_chat_messages
from ..playlist import (
    GlobalHotkey,
    PlaylistWorker,
    hotkey_display,
    qt_key_sequence,
    short_title,
)
from ..storage.history import HistoryStore
from ..storage.profile import Profile
from ..storage.pomodoro_stats import PomodoroStats
from ..storage.settings import Settings
from .dialogs import HelpDialog, HistoryDialog, PomodoroDialog, ProfileDialog, SettingsDialog
from .image_loader import pixmap_from_image_dewhite
from .speech_bubble import SpeechBubble
from .text_utils import split_sentences


class MaidPet(QWidget):
    def __init__(self):
        super().__init__()

        self.settings = Settings()
        self.profile = Profile()
        self.history = HistoryStore(HISTORY_PATH)

        self.system_prompt = self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)

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

        # 输入区
        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText("和 Maid 说点什么…（回车发送）")
        self.input_edit.returnPressed.connect(self.on_send)
        self.input_edit.setStyleSheet(
            "QLineEdit {"
            "  background: rgba(255,255,255,0.92);"
            "  border: 2px solid #ffb7c5;"
            "  border-radius: 14px;"
            "  padding: 6px 12px;"
            "  color: #3a2b35;"
            "  font-size: 13px;"
            "}"
        )
        self.send_btn = QPushButton("发送", self)
        self.send_btn.clicked.connect(self.on_send)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ffb7c5; color: white; border: none;"
            "  border-radius: 14px; padding: 6px 16px; font-size: 13px;"
            "}"
            "QPushButton:hover { background: #ff9db0; }"
            "QPushButton:disabled { background: #e0c3ca; }"
        )

        # 布局
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addWidget(self.char_label, 0, Qt.AlignHCenter)

        self.input_row = QWidget(self)
        input_layout = QHBoxLayout(self.input_row)
        input_layout.setContentsMargins(4, 0, 4, 4)
        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.send_btn, 0)
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
            parent=None,
        )

        # 拖拽
        self._drag_pos = None

        self.worker = None

        self._playlist_worker = None
        self._last_playlist_bvid = None
        self._last_playlist_at = 0.0
        self._setup_playlist_shortcut()

        # 恢复窗口位置
        self.adjustSize()
        self._restore_position()

        # 启动待机动画（眨眼），并在打开时问候
        self.state.start()
        self.scheduler.schedule_once("greet", 800, self.greet)

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
        text = self.input_edit.text().strip()
        if not text:
            return
        if self.worker and self.worker.isRunning():
            self.show_local("稍等，我还在想上一句呢～")
            return
        self.input_edit.clear()
        self.last_active = time.time()
        self._idle_greeted = False

        # 记录用户消息
        self.history.add("user", text)

        # 构建发给 API 的 messages
        messages = self._build_messages()

        self.send_btn.setEnabled(False)
        self.send_btn.setText("思考中…")
        self.state.begin_thinking()

        self.worker = ChatWorker(messages, self)
        self.worker.finished_ok.connect(self._on_reply)
        self.worker.failed.connect(self._on_reply_failed)
        self.worker.start()

    def _build_messages(self):
        return build_chat_messages(
            system_prompt=self.system_prompt,
            profile=self.profile,
            history=self.history,
            max_context_turns=MAX_CONTEXT_TURNS,
        )

    def _on_reply(self, content):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")
        self.history.add("maid", content)
        self.say(content)

    def _on_reply_failed(self, err):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")
        self.say(err)

    # ---- 本地说话（不走 API，不记历史） ----
    def show_local(self, text):
        self.notifications.show(text, record=False)

    def say(self, text, record=False):
        # 说话通道统一走通知管理器；嘴巴 / 眨眼由状态机决定。
        self.notifications.show(text, record=record)

    # ===================== 空闲 / 问候 =====================
    def greet(self):
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

    def _check_idle(self):
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

    # ===================== 番茄钟 =====================
    def open_pomodoro(self):
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
        act_greet.triggered.connect(self.greet)
        menu.addAction(act_greet)

        pomo_text = "番茄钟（进行中…）" if self._pomodoro_dialog.is_running else "番茄钟…"
        act_pomo = QAction(pomo_text, self)
        act_pomo.triggered.connect(self.open_pomodoro)
        menu.addAction(act_pomo)

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
        dlg.exec()

    def open_settings(self):
        dlg = SettingsDialog(self.settings, on_saved=self._on_settings_saved, parent=self)
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
        dlg.exec()

    def _on_profile_saved(self):
        name = self.profile.get("call_me") or self.profile.get("nickname") or "主人"
        self.show_local("档案已保存，%s，我会好好记住你的～" % name)

    def open_help(self):
        dlg = HelpDialog(parent=self)
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
            self, "确认", "确定要清空全部聊天记忆吗？角色会忘记之前的对话。"
        )
        if ret == QMessageBox.Yes:
            self.history.clear()
            self.show_local("好的，我已经把之前的对话都忘掉了～")

    def quit_app(self):
        self._save_position()
        self._teardown()
        QApplication.quit()

    def _teardown(self):
        """统一清理：停止全部定时任务、等待后台请求结束、关闭气泡。"""
        self.scheduler.shutdown()
        if self._global_hotkey is not None:
            self._global_hotkey.unregister()
        if self._playlist_worker is not None and self._playlist_worker.isRunning():
            self._playlist_worker.wait(2000)
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
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
