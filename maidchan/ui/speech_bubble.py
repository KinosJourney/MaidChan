# -*- coding: utf-8 -*-
"""对话气泡（打字机效果）。"""

import sys
import time
import webbrowser

from PySide6.QtCore import (
    Qt,
    QTimer,
    QPoint,
    QPropertyAnimation,
    QEasingCurve,
    QRectF,
)
from PySide6.QtGui import (
    QPixmap,
    QColor,
    QFont,
    QPainter,
    QFontMetrics,
    QPen,
)
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QGraphicsOpacityEffect,
)

from ..config.constants import TYPE_SPEED_MS
from .macos_window import show_on_all_spaces


class SpeechBubble(QWidget):
    """圆角对话气泡，支持打字机动画、点击补全、自动淡出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        # macOS 的 Qt.Tool 窗口会在应用失去焦点时隐藏。
        if sys.platform != "darwin":
            flags |= Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 主动对话可能在用户操作其它应用时弹出。顶层窗口默认会激活应用并
        # 抢走键盘焦点；明确要求只显示、不激活，鼠标点击气泡仍然可用。
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.label.setStyleSheet(
            "color: #3a2b35; background: transparent; padding: 14px 16px;"
        )
        f = QFont()
        f.setPointSize(13)
        self.label.setFont(f)
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)

        self.min_width = 180
        self.max_width = 280
        self.full_text = ""
        self.shown_chars = 0

        self.type_timer = QTimer(self)
        self.type_timer.timeout.connect(self._type_step)

        self.stay_timer = QTimer(self)
        self.stay_timer.setSingleShot(True)
        self.stay_timer.timeout.connect(self._on_stay_done)

        # 点击防手滑锁
        self._click_lock_until = 0.0

        # 淡入淡出
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.fade = QPropertyAnimation(self.opacity_effect, b"opacity")

        # 回调（由主窗口设置）
        self.on_sentence_typing = None   # 开始逐字（触发嘴巴动画）
        self.on_sentence_done = None     # 一句说完（停嘴）
        self.on_all_done = None          # 全部说完并淡出
        self.on_geometry_changed = None  # 气泡尺寸变化后重新定位

        # 多句队列
        self.sentences = []
        self.sentence_index = 0
        self.is_last_sentence = False

        # 可选：点击气泡打开的链接（查证 / 看原文）。为空则点击仅翻页。
        self.link = None

        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        show_on_all_spaces(self)

    # ---- 对外接口 ----
    def speak(self, sentences, link=None):
        """开始说多句话。sentences 是字符串列表。

        link 非空时，气泡整体可点击，点击会用浏览器打开该链接（查证 / 看原文），
        并显示放大镜标记与手型光标。每次说话都会重置 link。
        """
        self.sentences = [s for s in sentences if s.strip()]
        if not self.sentences:
            return
        self._set_link(link)
        self.sentence_index = 0
        self.opacity_effect.setOpacity(1.0)
        self._start_sentence(self.sentences[0])
        self.show()
        self.raise_()

    def _start_sentence(self, text):
        self.stay_timer.stop()
        self.fade.stop()
        self.opacity_effect.setOpacity(1.0)
        self.full_text = text
        self.shown_chars = 0
        self.is_last_sentence = self.sentence_index >= len(self.sentences) - 1
        self.label.setText("")
        self._relayout("")
        self.type_timer.start(TYPE_SPEED_MS)
        if self.on_sentence_typing:
            self.on_sentence_typing()

    def _type_step(self):
        self.shown_chars += 1
        if self.shown_chars >= len(self.full_text):
            self.shown_chars = len(self.full_text)
            self._finish_typing()
        text = self.full_text[: self.shown_chars]
        self._relayout(text)

    def _finish_typing(self):
        self.type_timer.stop()
        self._relayout(self.full_text)
        if self.on_sentence_done:
            self.on_sentence_done()
        # 允许点击进入下一句前，设置 0.5 秒锁
        self._click_lock_until = time.time() + 0.5
        # 自动停留：最后一句 3 秒，否则 2 秒
        stay_ms = 3000 if self.is_last_sentence else 2000
        self.stay_timer.start(stay_ms)

    def _on_stay_done(self):
        if self.is_last_sentence:
            self._fade_out()
        else:
            self._next_sentence()

    def _next_sentence(self):
        self.sentence_index += 1
        if self.sentence_index < len(self.sentences):
            self._start_sentence(self.sentences[self.sentence_index])
        else:
            self._fade_out()

    def _fade_out(self):
        self.stay_timer.stop()
        self.fade.stop()
        self.fade = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade.setDuration(600)
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)
        self.fade.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade.finished.connect(self._after_fade)
        self.fade.start()

    def _after_fade(self):
        self.hide()
        if self.on_all_done:
            self.on_all_done()

    # ---- 链接（查证 / 看原文） ----
    def _set_link(self, link):
        self.link = link or None
        cursor = Qt.PointingHandCursor if self.link else Qt.ArrowCursor
        self.setCursor(cursor)
        self.label.setCursor(cursor)

    def _open_link(self):
        if not self.link:
            return
        try:
            webbrowser.open(self.link, new=2)
        except Exception:
            pass

    # ---- 点击行为 ----
    def mousePressEvent(self, event):
        if self.type_timer.isActive():
            # 正在打字 -> 立即补全当前句
            self.type_timer.stop()
            self.shown_chars = len(self.full_text)
            self._finish_typing()
            return
        # 已打完，检查 0.5 秒防手滑锁
        if time.time() < self._click_lock_until:
            return
        # 有链接时，点击气泡打开浏览器查证 / 看原文（不翻页，交给计时器淡出）。
        if self.link:
            self._open_link()
            return
        # 进入下一句 / 结束
        self.stay_timer.stop()
        self._on_stay_done()

    # ---- 绘制圆角气泡背景 ----
    def _relayout(self, text):
        metrics = QFontMetrics(self.label.font())
        # 始终按完整句子预留空间，避免打字过程中气泡不断变形或裁掉末尾文字。
        measure_text = self.full_text or text or "　"
        longest_line = max(
            (metrics.horizontalAdvance(line or "　") for line in measure_text.splitlines()),
            default=metrics.horizontalAdvance("　"),
        )
        w = min(self.max_width, max(self.min_width, longest_line + 32))

        # 使用 QLabel 自己的换行规则测量高度，避免字体度量与实际渲染不一致。
        self.label.setText(measure_text)
        self.label.setFixedWidth(w)
        measured_height = self.label.heightForWidth(w)
        h = max(measured_height, metrics.lineSpacing() + 28) + 6

        self.label.setText(text)
        self.label.setGeometry(0, 0, w, h)
        self.resize(w, h + 12)  # 底部留出小尾巴空间
        self.update()
        if self.on_geometry_changed:
            self.on_geometry_changed()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height() - 12)
        # 气泡主体
        painter.setBrush(QColor(255, 253, 250, 240))
        painter.setPen(QPen(QColor(255, 183, 197, 220), 2))
        painter.drawRoundedRect(rect, 16, 16)
        # 小尾巴（指向下方角色）
        cx = self.width() / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 253, 250, 240))
        path_pts = [
            QPoint(int(cx - 10), int(self.height() - 13)),
            QPoint(int(cx + 10), int(self.height() - 13)),
            QPoint(int(cx), int(self.height() - 1)),
        ]
        painter.drawPolygon(path_pts)

        # 可点击查证时，在右上角画一个放大镜标记提示可点。
        if self.link:
            badge = QFont()
            badge.setPointSize(11)
            painter.setFont(badge)
            painter.setPen(QColor(232, 93, 117, 235))
            painter.drawText(
                QRectF(rect.right() - 26, rect.top() + 4, 22, 20),
                Qt.AlignCenter, "🔍",
            )
