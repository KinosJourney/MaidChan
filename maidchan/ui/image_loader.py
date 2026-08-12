# -*- coding: utf-8 -*-
"""图片处理：去白底 + 缩放。"""

import os
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

try:
    from PIL import Image  # 用于去白底
except ImportError:
    Image = None


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
