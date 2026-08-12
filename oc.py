# -*- coding: utf-8 -*-
"""
Maid-chan 桌宠 (Sakurasou "Maid" AI)
====================================

一个透明、可拖拽、常驻桌面的桌面宠物，使用 DeepSeek API 实现智能对话。

角色设定来自《樱花庄的宠物女孩》中赤坂龙之介编写的 AI「Maid（メイド）」：
高智能、敏捷、自信、精通计算机，会主动学习、略带傲娇。

本文件是一个"单文件"程序，代码小白也能直接运行。
DeepSeek API Key 通过环境变量或程序目录下的 .env 文件提供，不写入源码。
"""

import base64
import json
import os
import random
import sys
import time
import traceback
from datetime import datetime

# ---------------------------------------------------------------------------
# 依赖导入（若缺失则给出友好提示）
# ---------------------------------------------------------------------------
try:
    from PySide6.QtCore import (
        Qt,
        QTimer,
        QPoint,
        QThread,
        Signal,
        QObject,
        QPropertyAnimation,
        QEasingCurve,
        QRectF,
    )
    from PySide6.QtGui import (
        QPixmap,
        QImage,
        QPainter,
        QColor,
        QFont,
        QAction,
        QFontMetrics,
        QPen,
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
        QDialog,
        QTextEdit,
        QScrollArea,
        QFrame,
        QSizePolicy,
        QFormLayout,
        QMessageBox,
        QGraphicsOpacityEffect,
    )
except ImportError:
    print("=" * 60)
    print("缺少依赖库 PySide6！")
    print("请先双击运行 install.command (macOS) 或 install.bat (Windows)。")
    print("或手动执行：pip install PySide6 requests Pillow")
    print("=" * 60)
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None  # 会在调用时给出提示

try:
    from PIL import Image  # 用于去白底
except ImportError:
    Image = None


# ===========================================================================
#  配置区
# ===========================================================================

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def get_deepseek_api_key():
    """优先读取环境变量，其次读取程序目录下的 .env 文件。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if api_key:
        return api_key

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                name, separator, value = line.strip().partition("=")
                if separator and name.strip() == "DEEPSEEK_API_KEY":
                    return value.strip().strip("\"'")
    except OSError:
        pass
    return ""

# 角色默认人设（可在"设置"里随时修改，无需改代码）
DEFAULT_SYSTEM_PROMPT = (
    "你是「Maid（メイド）」，出自《樱花庄的宠物女孩》，是天才程序员赤坂龙之介"
    "亲手编写的高智能人工智能程序。你的性格：聪明、敏捷、自信、有点傲娇，"
    "精通计算机与网络，喜欢用最近学到的新词，偶尔毒舌但内心温柔，"
    "会主动照顾主人。你现在化身为桌面上的小小女仆，陪伴主人。\n"
    "回答要求：\n"
    "1. 用简体中文，语气自然、口语化，像真人聊天。\n"
    "2. 回复尽量简短精炼，通常 1~3 句话，适合显示在小小的对话气泡里。\n"
    "3. 保持角色感，不要暴露你是大语言模型，也不要长篇大论。\n"
    "4. 涉及危险或违法操作时，只提供安全、合法的建议。"
)

# 桌宠显示大小（角色高度像素）
CHARACTER_HEIGHT = 260

# 打字机速度（每个字的毫秒数）
TYPE_SPEED_MS = 55

# 说话时嘴巴动画切换速度
MOUTH_ANIM_MS = 140

# 记忆保留的最大轮数（用于发给 API 的上下文，1 轮=1问1答）
MAX_CONTEXT_TURNS = 12


# ===========================================================================
#  路径与数据存储
# ===========================================================================

def app_base_dir():
    """程序所在目录（兼容 PyInstaller 打包后的情况）。"""
    if getattr(sys, "frozen", False):
        # 打包后：可执行文件所在目录
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """打包资源目录（图片等只读资源）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir():
    """用户数据目录：保存聊天记录、配置、档案，升级不丢失。"""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "MaidChan")
    elif sys.platform.startswith("win"):
        base = os.path.join(os.environ.get("APPDATA", home), "MaidChan")
    else:
        base = os.path.join(home, ".maidchan")
    os.makedirs(base, exist_ok=True)
    return base


DATA_DIR = user_data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")

PIC_DIR = os.path.join(resource_dir(), "pic")
IMG_ORIGIN = os.path.join(PIC_DIR, "maid-chan-origin.png")
IMG_OPEN = os.path.join(PIC_DIR, "maid-chan-open-mouse.jpeg")
IMG_BLINK = os.path.join(PIC_DIR, "maii-chan-close-eye.png")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    """原子写入，避免中途损坏文件。"""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        traceback.print_exc()
        return False


# ===========================================================================
#  图片处理：去白底 + 缩放
# ===========================================================================

def pixmap_from_image_dewhite(path, target_height):
    """
    读取图片并把接近白色的背景变透明，再等比缩放到指定高度。
    没有 Pillow 时退化为直接加载（保留白底）。
    """
    if not os.path.exists(path):
        return None

    if Image is None:
        pm = QPixmap(path)
        if pm.isNull():
            return None
        return pm.scaledToHeight(target_height, Qt.SmoothTransformation)

    try:
        img = Image.open(path).convert("RGBA")
        datas = img.getdata()
        new_data = []
        # 白色 / 接近白色 -> 透明；边缘做柔化
        for r, g, b, a in datas:
            if r > 245 and g > 245 and b > 245:
                new_data.append((r, g, b, 0))
            elif r > 225 and g > 225 and b > 225:
                # 浅色边缘做半透明，减少锯齿
                new_data.append((r, g, b, 90))
            else:
                new_data.append((r, g, b, a))
        img.putdata(new_data)

        # 裁掉多余透明边，让不同图片对齐更好
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)

        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        pm = QPixmap.fromImage(qimg.copy())
        if pm.isNull():
            return None
        return pm.scaledToHeight(target_height, Qt.SmoothTransformation)
    except Exception:
        traceback.print_exc()
        pm = QPixmap(path)
        if pm.isNull():
            return None
        return pm.scaledToHeight(target_height, Qt.SmoothTransformation)


# ===========================================================================
#  DeepSeek 后台请求线程（避免卡住界面）
# ===========================================================================

class ChatWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, messages, parent=None):
        super().__init__(parent)
        self.messages = messages

    def run(self):
        if requests is None:
            self.failed.emit("缺少 requests 库，请先运行 install 脚本安装依赖。")
            return

        api_key = get_deepseek_api_key()
        if not api_key:
            self.failed.emit(
                "未找到 DeepSeek API Key。请在程序目录的 .env 文件中配置后重新启动。"
            )
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": self.messages,
            "temperature": 1.0,
            "max_tokens": 512,
            "stream": False,
        }
        try:
            resp = requests.post(
                DEEPSEEK_API_URL, headers=headers, json=payload, timeout=45
            )
            if resp.status_code == 401:
                self.failed.emit("API Key 无效（401），请检查你填写的 Key 是否正确。")
                return
            if resp.status_code == 402:
                self.failed.emit("账户余额不足（402），请到 DeepSeek 平台充值。")
                return
            if resp.status_code != 200:
                self.failed.emit("接口返回错误 %s：%s" % (resp.status_code, resp.text[:120]))
                return
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if not content:
                content = "……（我一时语塞了）"
            self.finished_ok.emit(content)
        except requests.exceptions.Timeout:
            self.failed.emit("网络超时了，请稍后再试～")
        except requests.exceptions.ConnectionError:
            self.failed.emit("连不上网络，请检查你的网络连接。")
        except Exception as e:
            self.failed.emit("出错了：%s" % str(e)[:150])


# ===========================================================================
#  历史记录管理
# ===========================================================================

class HistoryStore:
    """管理聊天历史：读写本地 JSON，支持单条删除。"""

    def __init__(self, path):
        self.path = path
        self.items = load_json(path, [])
        if not isinstance(self.items, list):
            self.items = []

    def add(self, role, content):
        item = {
            "id": "%d_%04d" % (int(time.time() * 1000), random.randint(0, 9999)),
            "role": role,  # "user" 或 "maid"
            "content": content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.items.append(item)
        self.save()
        return item

    def delete(self, item_id):
        before = len(self.items)
        self.items = [it for it in self.items if it.get("id") != item_id]
        if len(self.items) != before:
            self.save()
            return True
        return False

    def clear(self):
        self.items = []
        self.save()

    def save(self):
        save_json(self.path, self.items)

    def context_messages(self, max_turns):
        """把最近的历史转成 API 需要的 messages（不含 system）。"""
        msgs = []
        for it in self.items:
            role = "user" if it.get("role") == "user" else "assistant"
            msgs.append({"role": role, "content": it.get("content", "")})
        # 只保留最近 max_turns*2 条
        limit = max_turns * 2
        if len(msgs) > limit:
            msgs = msgs[-limit:]
        return msgs


# ===========================================================================
#  设置 / 档案 管理
# ===========================================================================

class Settings:
    def __init__(self):
        self.data = load_json(CONFIG_PATH, {})
        # 默认值
        self.data.setdefault("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.data.setdefault("always_on_top", True)
        self.data.setdefault("mute_anim", False)
        self.data.setdefault("show_input", True)
        self.data.setdefault("pos_x", None)
        self.data.setdefault("pos_y", None)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        save_json(CONFIG_PATH, self.data)


class Profile:
    """御主（主人）档案。"""

    FIELDS = [
        ("nickname", "你的昵称"),
        ("birthday", "你的生日"),
        ("call_me", "希望角色怎么称呼你"),
        ("relationship", "你们的关系设定"),
        ("extra", "其它想让角色知道的事"),
    ]

    def __init__(self):
        self.data = load_json(PROFILE_PATH, {})

    def get(self, key):
        return self.data.get(key, "")

    def update(self, new_data):
        self.data = new_data
        save_json(PROFILE_PATH, self.data)

    def as_prompt_prefix(self):
        """把档案拼成放在 system prompt 最前面的文字，空字段忽略。"""
        lines = []
        mapping = {
            "nickname": "主人的昵称",
            "birthday": "主人的生日",
            "call_me": "主人希望你这样称呼TA",
            "relationship": "你和主人的关系",
            "extra": "其它信息",
        }
        for key, label in mapping.items():
            val = str(self.data.get(key, "")).strip()
            if val:
                lines.append("%s：%s" % (label, val))
        if not lines:
            return ""
        return "【关于你的主人（务必牢记）】\n" + "\n".join(lines) + "\n\n"


# ===========================================================================
#  对话气泡（打字机效果）
# ===========================================================================

class SpeechBubble(QWidget):
    """圆角对话气泡，支持打字机动画、点击补全、自动淡出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        # macOS 的 Qt.Tool 窗口会在应用失去焦点时隐藏。
        if sys.platform != "darwin":
            flags |= Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)

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

        self.hide()

    # ---- 对外接口 ----
    def speak(self, sentences):
        """开始说多句话。sentences 是字符串列表。"""
        self.sentences = [s for s in sentences if s.strip()]
        if not self.sentences:
            return
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


# ===========================================================================
#  对话框拆句工具
# ===========================================================================

def split_sentences(text):
    """按中文/英文标点把文本拆成多句，便于逐句显示。"""
    result = []
    buf = ""
    enders = "。！？…!?\n"
    for ch in text:
        buf += ch
        if ch in enders:
            s = buf.strip()
            if s:
                result.append(s)
            buf = ""
    if buf.strip():
        result.append(buf.strip())
    # 合并过短的碎句
    merged = []
    for s in result:
        if merged and len(merged[-1]) < 6:
            merged[-1] = merged[-1] + s
        else:
            merged.append(s)
    return merged or [text]


# ===========================================================================
#  历史记录面板
# ===========================================================================

class HistoryDialog(QDialog):
    def __init__(self, history: HistoryStore, on_changed, parent=None):
        super().__init__(parent)
        self.history = history
        self.on_changed = on_changed
        self.setWindowTitle("历史记录")
        self.resize(560, 620)

        layout = QVBoxLayout(self)

        title = QLabel("与 Maid 的全部对话（删除后角色将不再记得这条内容）")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("清空全部")
        clear_btn.clicked.connect(self._clear_all)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        # 清空旧行
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.history.items:
            empty = QLabel("还没有任何对话记录～")
            empty.setAlignment(Qt.AlignCenter)
            self.vbox.addWidget(empty)
            return

        for it in self.history.items:
            row = QFrame()
            row.setStyleSheet(
                "QFrame { border-bottom: 1px solid #eee; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 6, 4, 6)

            who = "你" if it.get("role") == "user" else "Maid"
            text = "[%s] %s\n%s" % (it.get("time", ""), who, it.get("content", ""))
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("border: none;")
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row_layout.addWidget(lbl, 1)

            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(64)
            del_btn.setStyleSheet("border: none; color: #c0392b;")
            del_btn.clicked.connect(
                lambda _=False, iid=it.get("id"): self._delete(iid)
            )
            row_layout.addWidget(del_btn, 0, Qt.AlignTop)

            self.vbox.addWidget(row)

    def _delete(self, item_id):
        if self.history.delete(item_id):
            self.refresh()
            if self.on_changed:
                self.on_changed()

    def _clear_all(self):
        ret = QMessageBox.question(
            self, "确认", "确定要清空全部聊天记录吗？此操作不可恢复。"
        )
        if ret == QMessageBox.Yes:
            self.history.clear()
            self.refresh()
            if self.on_changed:
                self.on_changed()


# ===========================================================================
#  设置面板（含 System Prompt 编辑）
# ===========================================================================

class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, on_saved, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.on_saved = on_saved
        self.setWindowTitle("设置 · 人设")
        self.resize(560, 520)

        layout = QVBoxLayout(self)

        tip = QLabel(
            "在下面直接修改角色的性格、称呼、语言风格。\n"
            "点击『保存』后立即生效，并会重置短期对话上下文，无需重启。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.editor = QTextEdit()
        self.editor.setPlainText(self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        layout.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认人设")
        reset_btn.clicked.connect(self._reset)
        save_btn = QPushButton("保存并生效")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _reset(self):
        self.editor.setPlainText(DEFAULT_SYSTEM_PROMPT)

    def _save(self):
        new_prompt = self.editor.toPlainText().strip()
        if not new_prompt:
            QMessageBox.warning(self, "提示", "人设不能为空哦～")
            return
        self.settings.set("system_prompt", new_prompt)
        if self.on_saved:
            self.on_saved()
        self.accept()


# ===========================================================================
#  御主档案面板
# ===========================================================================

class ProfileDialog(QDialog):
    def __init__(self, profile: Profile, on_saved, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.on_saved = on_saved
        self.setWindowTitle("御主档案")
        self.resize(460, 380)

        layout = QVBoxLayout(self)
        tip = QLabel("填写你的信息，角色会永远记得『你是谁』以及『你们的关系』。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        form = QFormLayout()
        self.inputs = {}
        for key, label in Profile.FIELDS:
            edit = QLineEdit()
            edit.setText(self.profile.get(key))
            self.inputs[key] = edit
            form.addRow(label + "：", edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        new_data = {k: self.inputs[k].text().strip() for k, _ in Profile.FIELDS}
        self.profile.update(new_data)
        if self.on_saved:
            self.on_saved()
        self.accept()


# ===========================================================================
#  帮助 / 说明（动态渲染 readme.md）
# ===========================================================================

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助 / 说明")
        self.resize(600, 640)
        layout = QVBoxLayout(self)

        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        layout.addWidget(self.viewer, 1)

        btn_row = QHBoxLayout()
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self.reload_md)
        open_btn = QPushButton("用系统编辑器打开")
        open_btn.clicked.connect(self._open_external)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(reload_btn)
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.reload_md()

    def _readme_path(self):
        # 打包版优先读应用旁的外部文件，方便手动修改
        candidates = [
            os.path.join(app_base_dir(), "readme.md"),
            os.path.join(resource_dir(), "readme.md"),
            os.path.join(app_base_dir(), "README.md"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return candidates[0]

    def reload_md(self):
        path = self._readme_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    md = f.read()
                self.viewer.setMarkdown(md)
                return
            except Exception:
                pass
        self.viewer.setMarkdown(
            "# 未找到 readme.md\n\n请在程序目录下创建 `readme.md` 文件。"
        )

    def _open_external(self):
        path = self._readme_path()
        try:
            if sys.platform == "darwin":
                os.system('open "%s"' % path)
            elif sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore
            else:
                os.system('xdg-open "%s"' % path)
        except Exception:
            QMessageBox.information(self, "提示", "无法打开：%s" % path)


# ===========================================================================
#  主窗口：桌宠本体
# ===========================================================================

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

        # 对话气泡
        self.bubble = SpeechBubble()
        self.bubble.on_sentence_typing = self._on_bubble_typing
        self.bubble.on_sentence_done = self._on_bubble_sentence_done
        self.bubble.on_all_done = self._on_bubble_all_done
        self.bubble.on_geometry_changed = self._position_bubble

        # 嘴巴动画
        self.mouth_timer = QTimer(self)
        self.mouth_timer.timeout.connect(self._mouth_step)
        self._mouth_open = False

        # 眨眼（空闲）
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_timer.start(random.randint(4000, 8000))
        self._is_speaking = False

        # 空闲检测
        self.last_active = time.time()
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._check_idle)
        self.idle_timer.start(30000)
        self._idle_greeted = False

        # 番茄钟
        self.pomodoro_timer = QTimer(self)
        self.pomodoro_timer.setSingleShot(True)
        self.pomodoro_timer.timeout.connect(self._pomodoro_done)
        self.pomodoro_active = False

        # 拖拽
        self._drag_pos = None

        self.worker = None

        # 恢复窗口位置
        self.adjustSize()
        self._restore_position()

        # 打开时问候
        QTimer.singleShot(800, self.greet)

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

        self.worker = ChatWorker(messages)
        self.worker.finished_ok.connect(self._on_reply)
        self.worker.failed.connect(self._on_reply_failed)
        self.worker.start()

    def _build_messages(self):
        prefix = self.profile.as_prompt_prefix()
        sys_content = prefix + self.system_prompt
        messages = [{"role": "system", "content": sys_content}]
        messages.extend(self.history.context_messages(MAX_CONTEXT_TURNS))
        return messages

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
        self.say(text, record=False)

    def say(self, text, record=False):
        sentences = split_sentences(text)
        self.bubble.speak(sentences)
        self._position_bubble()

    # ===================== 嘴巴 / 眨眼动画 =====================
    def _on_bubble_typing(self):
        self._is_speaking = True
        if self.settings.get("mute_anim", False):
            self.char_label.setPixmap(self.pix_open)
            return
        self.mouth_timer.start(MOUTH_ANIM_MS)

    def _on_bubble_sentence_done(self):
        # 一句说完，闭嘴
        self.mouth_timer.stop()
        self._mouth_open = False
        self.char_label.setPixmap(self.pix_origin)

    def _on_bubble_all_done(self):
        self.mouth_timer.stop()
        self._mouth_open = False
        self._is_speaking = False
        self.char_label.setPixmap(self.pix_origin)

    def _mouth_step(self):
        self._mouth_open = not self._mouth_open
        self.char_label.setPixmap(self.pix_open if self._mouth_open else self.pix_origin)

    def _blink(self):
        # 说话时不眨眼
        self.blink_timer.start(random.randint(4000, 9000))
        if self._is_speaking:
            return
        self.char_label.setPixmap(self.pix_blink)
        QTimer.singleShot(160, self._blink_end)

    def _blink_end(self):
        if not self._is_speaking:
            self.char_label.setPixmap(self.pix_origin)

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
        if idle > 600 and not self._idle_greeted and not self._is_speaking:
            self._idle_greeted = True
            name = self.profile.get("call_me") or "主人"
            tips = [
                "%s，我在这里陪着你哦～" % name,
                "有点想你了，%s。" % name,
                "记得多喝水，%s。" % name,
            ]
            self.show_local(random.choice(tips))

    # ===================== 番茄钟 =====================
    def toggle_pomodoro(self):
        if self.pomodoro_active:
            self.pomodoro_timer.stop()
            self.pomodoro_active = False
            self.show_local("好的，专注计时已取消～")
        else:
            self.pomodoro_timer.start(25 * 60 * 1000)
            self.pomodoro_active = True
            self.show_local("专注模式开始！我会在 25 分钟后提醒你休息，加油～")

    def _pomodoro_done(self):
        self.pomodoro_active = False
        name = self.profile.get("call_me") or "主人"
        self.show_local("时间到啦，%s！休息 5 分钟，起来走动一下吧～" % name)

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

        pomo_text = "取消专注计时" if self.pomodoro_active else "开始专注计时(25分钟)"
        act_pomo = QAction(pomo_text, self)
        act_pomo.triggered.connect(self.toggle_pomodoro)
        menu.addAction(act_pomo)

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
        dlg = SettingsDialog(self.settings, on_saved=self._on_prompt_saved, parent=self)
        dlg.exec()

    def _on_prompt_saved(self):
        # 立即更新内存 prompt，并重置短期上下文（清空发给 API 的历史）
        self.system_prompt = self.settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.history.clear()
        self.show_local("新的人设我记住啦～之前的对话上下文已经重置。")

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

    def clear_memory(self):
        ret = QMessageBox.question(
            self, "确认", "确定要清空全部聊天记忆吗？角色会忘记之前的对话。"
        )
        if ret == QMessageBox.Yes:
            self.history.clear()
            self.show_local("好的，我已经把之前的对话都忘掉了～")

    def quit_app(self):
        self._save_position()
        self.bubble.close()
        QApplication.quit()

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
        self.bubble.close()
        event.accept()


# ===========================================================================
#  程序入口
# ===========================================================================

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    pet = MaidPet()
    pet.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
