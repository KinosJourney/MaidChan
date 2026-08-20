# -*- coding: utf-8 -*-
"""可复用的提示音组件。

番茄钟完成、待办到点提醒等都用同一段程序生成的「叮咚」双音。
生成的 WAV 缓存在系统临时目录，避免重复合成。QtMultimedia 不可用时静默降级。
"""

import os
import struct
import tempfile
import wave

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # QtMultimedia 不可用时降级为无声
    QUrl = None
    QSoundEffect = None

_CACHE_FILENAME = "maidchan_chime_ding.wav"


class ChimePlayer:
    """播放提示音的小组件。多个功能可各持一个实例，共用同一份 WAV 文件。"""

    def __init__(self, parent=None, volume=0.6):
        self._parent = parent
        self._volume = volume
        self._sound = None
        self._path = None

    def play(self):
        if QSoundEffect is None or QUrl is None:
            return
        path = self._sound_file()
        if not path:
            return
        if self._sound is None:
            self._sound = QSoundEffect(self._parent)
        self._sound.setSource(QUrl.fromLocalFile(path))
        self._sound.setVolume(self._volume)
        self._sound.play()

    # ---- 音频文件 ----
    def _sound_file(self):
        """生成（或复用）提示音 WAV 文件，返回路径；失败返回 None。"""
        if self._path and os.path.exists(self._path):
            return self._path
        try:
            path = os.path.join(tempfile.gettempdir(), _CACHE_FILENAME)
            if not os.path.exists(path):
                self._generate_ding(path)
            self._path = path
            return path
        except Exception:
            return None

    @staticmethod
    def _generate_ding(path):
        """生成一段简短的「叮咚」双音提示音。"""
        import math

        framerate = 44100
        amplitude = 18000
        frames = bytearray()
        # 两个音调：高音 -> 低音
        for freq, dur in ((880.0, 0.18), (660.0, 0.28)):
            count = int(framerate * dur)
            for i in range(count):
                # 淡出包络，避免爆音
                env = 1.0 - (i / count)
                sample = int(
                    amplitude * env * math.sin(2 * math.pi * freq * i / framerate)
                )
                frames += struct.pack("<h", sample)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(bytes(frames))
