# -*- coding: utf-8 -*-
"""程序入口：初始化 QApplication 并显示桌宠。"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config.paths import APP_ICON
from .ui.maid_pet import MaidPet
from .ui.macos_window import use_accessory_activation_policy


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    use_accessory_activation_policy()
    app.setWindowIcon(QIcon(APP_ICON))
    app.setQuitOnLastWindowClosed(True)

    pet = MaidPet()
    pet.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
