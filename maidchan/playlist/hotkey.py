# -*- coding: utf-8 -*-
"""全局快捷键：即使桌宠没有焦点也能触发。

- macOS 使用 Carbon RegisterEventHotKey（不需要辅助功能权限）
- Windows 使用 RegisterHotKey
- 注册失败时仍可在桌宠窗口聚焦时用 QAction 快捷键
"""

import ctypes
import sys
import traceback

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QKeySequence

# macOS ANSI 字母键码（A-Z）
_MAC_LETTER_KEYCODES = {
    "A": 0x00,
    "S": 0x01,
    "D": 0x02,
    "F": 0x03,
    "H": 0x04,
    "G": 0x05,
    "Z": 0x06,
    "X": 0x07,
    "C": 0x08,
    "V": 0x09,
    "B": 0x0B,
    "Q": 0x0C,
    "W": 0x0D,
    "E": 0x0E,
    "R": 0x0F,
    "Y": 0x10,
    "T": 0x11,
    "O": 0x1F,
    "U": 0x20,
    "I": 0x22,
    "P": 0x23,
    "L": 0x25,
    "J": 0x26,
    "K": 0x28,
    "N": 0x2D,
    "M": 0x2E,
}

# Carbon 修饰键（RegisterEventHotKey 用）
_MAC_CMD = 0x0100
_MAC_SHIFT = 0x0200
_MAC_OPTION = 0x0800
_MAC_CONTROL = 0x1000

# Windows
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312


def parse_hotkey(spec):
    """把 ``Ctrl+Shift+P`` 解析为 (modifier_set, letter)。

    ``Ctrl`` 一律表示物理 Control 键（macOS 上不是 Command）。
    """
    if not spec:
        raise ValueError("empty hotkey")
    parts = [p.strip() for p in str(spec).split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("hotkey needs a modifier")
    letter = parts[-1].upper()
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError("hotkey key must be A-Z")
    mods = set()
    for raw in parts[:-1]:
        name = raw.strip().lower()
        if name in ("ctrl", "control"):
            mods.add("ctrl")
        elif name == "shift":
            mods.add("shift")
        elif name in ("alt", "option"):
            mods.add("alt")
        elif name in ("meta", "cmd", "command", "win"):
            mods.add("meta")
        else:
            raise ValueError("unknown modifier: %s" % raw)
    if not mods:
        raise ValueError("hotkey needs a modifier")
    return mods, letter


def qt_key_sequence(spec):
    """生成与全局快捷键一致的 QKeySequence（Mac 上 Ctrl=物理 Control）。"""
    mods, letter = parse_hotkey(spec)
    tokens = []
    if "ctrl" in mods:
        tokens.append("Meta" if sys.platform == "darwin" else "Ctrl")
    if "shift" in mods:
        tokens.append("Shift")
    if "alt" in mods:
        tokens.append("Alt")
    if "meta" in mods:
        tokens.append("Ctrl" if sys.platform == "darwin" else "Meta")
    tokens.append(letter)
    return QKeySequence("+".join(tokens))


def hotkey_display(spec):
    """菜单 / 说明里展示的快捷键文本。"""
    mods, letter = parse_hotkey(spec)
    if sys.platform == "darwin":
        bits = []
        if "ctrl" in mods:
            bits.append("⌃")
        if "alt" in mods:
            bits.append("⌥")
        if "shift" in mods:
            bits.append("⇧")
        if "meta" in mods:
            bits.append("⌘")
        return "".join(bits) + letter
    bits = []
    if "ctrl" in mods:
        bits.append("Ctrl")
    if "alt" in mods:
        bits.append("Alt")
    if "shift" in mods:
        bits.append("Shift")
    if "meta" in mods:
        bits.append("Win")
    bits.append(letter)
    return "+".join(bits)


class _WinHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id, on_hotkey):
        super().__init__()
        self._id = hotkey_id
        self._on = on_hotkey

    def nativeEventFilter(self, eventType, message):
        et = eventType.decode() if isinstance(eventType, (bytes, bytearray)) else str(eventType)
        if et not in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            return False, 0
        try:
            addr = int(message)
        except Exception:
            return False, 0
        msg = ctypes.wintypes.MSG.from_address(addr)
        if msg.message == _WM_HOTKEY and int(msg.wParam) == self._id:
            self._on()
            return True, 0
        return False, 0


class GlobalHotkey(QObject):
    """系统级快捷键。``activated`` 在主线程发出。"""

    activated = Signal()

    def __init__(self, spec, widget=None, parent=None):
        super().__init__(parent)
        self._spec = spec
        self._widget = widget
        self._mac_hotkey_ref = None
        self._mac_handler_ref = None
        self._mac_callback = None
        self._win_filter = None
        self._win_hwnd = None
        self._win_id = 1
        self.registered = False
        try:
            self._register()
        except Exception:
            traceback.print_exc()

    def unregister(self):
        if sys.platform == "darwin":
            self._unregister_mac()
        elif sys.platform.startswith("win"):
            self._unregister_win()
        self.registered = False

    def _fire(self):
        self.activated.emit()

    def _register(self):
        mods, letter = parse_hotkey(self._spec)
        if sys.platform == "darwin":
            self._register_mac(mods, letter)
        elif sys.platform.startswith("win"):
            self._register_win(mods, letter)

    # ---- macOS Carbon ----
    def _register_mac(self, mods, letter):
        import ctypes.util

        keycode = _MAC_LETTER_KEYCODES.get(letter)
        if keycode is None:
            raise ValueError("unsupported key: %s" % letter)
        native_mods = 0
        if "ctrl" in mods:
            native_mods |= _MAC_CONTROL
        if "shift" in mods:
            native_mods |= _MAC_SHIFT
        if "alt" in mods:
            native_mods |= _MAC_OPTION
        if "meta" in mods:
            native_mods |= _MAC_CMD

        libname = ctypes.util.find_library("Carbon")
        if not libname:
            raise RuntimeError("Carbon not found")
        carbon = ctypes.cdll.LoadLibrary(libname)

        os_status = ctypes.c_int32
        event_ref = ctypes.c_void_p
        target_ref = ctypes.c_void_p

        class EventTypeSpec(ctypes.Structure):
            _fields_ = [
                ("eventClass", ctypes.c_uint32),
                ("eventKind", ctypes.c_uint32),
            ]

        class EventHotKeyID(ctypes.Structure):
            _fields_ = [
                ("signature", ctypes.c_uint32),
                ("id", ctypes.c_uint32),
            ]

        handler_upp = ctypes.CFUNCTYPE(
            os_status, event_ref, event_ref, ctypes.c_void_p
        )

        carbon.GetApplicationEventTarget.restype = target_ref
        carbon.GetApplicationEventTarget.argtypes = []
        carbon.InstallEventHandler.restype = os_status
        carbon.InstallEventHandler.argtypes = [
            target_ref,
            handler_upp,
            ctypes.c_uint32,
            ctypes.POINTER(EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(event_ref),
        ]
        carbon.RegisterEventHotKey.restype = os_status
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            EventHotKeyID,
            target_ref,
            ctypes.c_uint32,
            ctypes.POINTER(event_ref),
        ]
        carbon.UnregisterEventHotKey.restype = os_status
        carbon.UnregisterEventHotKey.argtypes = [event_ref]
        carbon.RemoveEventHandler.restype = os_status
        carbon.RemoveEventHandler.argtypes = [event_ref]

        def _handler(_next, _event, _user):
            self._fire()
            return 0

        self._mac_callback = handler_upp(_handler)
        self._carbon = carbon

        types = EventTypeSpec()
        types.eventClass = 0x6B657962  # 'keyb'
        types.eventKind = 5  # kEventHotKeyPressed
        handler_ref = event_ref()
        err = carbon.InstallEventHandler(
            carbon.GetApplicationEventTarget(),
            self._mac_callback,
            1,
            ctypes.byref(types),
            None,
            ctypes.byref(handler_ref),
        )
        if err != 0:
            raise RuntimeError("InstallEventHandler failed: %s" % err)
        self._mac_handler_ref = handler_ref

        hotkey_id = EventHotKeyID()
        hotkey_id.signature = 0x4D414944  # 'MAID'
        hotkey_id.id = 1
        hotkey_ref = event_ref()
        err = carbon.RegisterEventHotKey(
            keycode,
            native_mods,
            hotkey_id,
            carbon.GetApplicationEventTarget(),
            0,
            ctypes.byref(hotkey_ref),
        )
        if err != 0:
            carbon.RemoveEventHandler(handler_ref)
            self._mac_handler_ref = None
            raise RuntimeError("RegisterEventHotKey failed: %s" % err)
        self._mac_hotkey_ref = hotkey_ref
        self.registered = True

    def _unregister_mac(self):
        carbon = getattr(self, "_carbon", None)
        if carbon is None:
            return
        if self._mac_hotkey_ref:
            try:
                carbon.UnregisterEventHotKey(self._mac_hotkey_ref)
            except Exception:
                pass
            self._mac_hotkey_ref = None
        if self._mac_handler_ref:
            try:
                carbon.RemoveEventHandler(self._mac_handler_ref)
            except Exception:
                pass
            self._mac_handler_ref = None
        self._mac_callback = None

    # ---- Windows ----
    def _register_win(self, mods, letter):
        from ctypes import wintypes  # noqa: F401

        native_mods = _MOD_NOREPEAT
        if "ctrl" in mods:
            native_mods |= _MOD_CONTROL
        if "shift" in mods:
            native_mods |= _MOD_SHIFT
        if "alt" in mods:
            native_mods |= _MOD_ALT
        if "meta" in mods:
            native_mods |= _MOD_WIN
        vk = ord(letter)

        hwnd = 0
        if self._widget is not None:
            hwnd = int(self._widget.winId())
        self._win_hwnd = hwnd
        ok = ctypes.windll.user32.RegisterHotKey(
            hwnd, self._win_id, native_mods, vk
        )
        if not ok:
            raise RuntimeError("RegisterHotKey failed")

        from PySide6.QtWidgets import QApplication

        self._win_filter = _WinHotkeyFilter(self._win_id, self._fire)
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("no QApplication")
        app.installNativeEventFilter(self._win_filter)
        self.registered = True

    def _unregister_win(self):
        if self._win_hwnd is None:
            return
        try:
            ctypes.windll.user32.UnregisterHotKey(self._win_hwnd, self._win_id)
        except Exception:
            pass
        self._win_filter = None
        self._win_hwnd = None
