"""macOS 原生窗口行为辅助函数。"""

import ctypes
import ctypes.util
import sys


# https://developer.apple.com/documentation/appkit/nswindowcollectionbehavior
_CAN_JOIN_ALL_SPACES = 1 << 0
_STATIONARY = 1 << 4
_FULL_SCREEN_AUXILIARY = 1 << 8
_ACCESSORY_ACTIVATION_POLICY = 1


def use_accessory_activation_policy():
    """将进程设为 macOS 桌面挂件应用；须在创建首个窗口前调用。"""
    if sys.platform != "darwin":
        return

    try:
        objc_path = ctypes.util.find_library("objc")
        if not objc_path:
            return
        objc = ctypes.CDLL(objc_path)

        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        selector = objc.sel_registerName
        selector.argtypes = [ctypes.c_char_p]
        selector.restype = ctypes.c_void_p

        send_pointer = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(("objc_msgSend", objc))
        send_bool_integer = ctypes.CFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long
        )(("objc_msgSend", objc))

        application_class = objc.objc_getClass(b"NSApplication")
        application = send_pointer(
            application_class, selector(b"sharedApplication")
        )
        if application:
            send_bool_integer(
                application,
                selector(b"setActivationPolicy:"),
                _ACCESSORY_ACTIVATION_POLICY,
            )
    except (AttributeError, OSError, TypeError, ValueError):
        return


def show_on_all_spaces(widget):
    """让 Qt 窗口出现在 macOS 的所有桌面空间及全屏空间中。"""
    if sys.platform != "darwin":
        return

    try:
        objc_path = ctypes.util.find_library("objc")
        if not objc_path:
            return
        objc = ctypes.CDLL(objc_path)

        selector = objc.sel_registerName
        selector.argtypes = [ctypes.c_char_p]
        selector.restype = ctypes.c_void_p

        send_pointer = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(("objc_msgSend", objc))
        send_integer = ctypes.CFUNCTYPE(
            ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p
        )(("objc_msgSend", objc))
        send_void_integer = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong
        )(("objc_msgSend", objc))

        native_view = int(widget.winId())
        native_window = send_pointer(native_view, selector(b"window"))
        if not native_window:
            return

        behavior = send_integer(native_window, selector(b"collectionBehavior"))
        behavior |= (
            _CAN_JOIN_ALL_SPACES | _STATIONARY | _FULL_SCREEN_AUXILIARY
        )
        send_void_integer(
            native_window, selector(b"setCollectionBehavior:"), behavior
        )
    except (AttributeError, OSError, TypeError, ValueError):
        # 原生接口不可用时保留 Qt 的默认窗口行为。
        return
