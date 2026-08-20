# -*- coding: utf-8 -*-
"""麦克风录音（基于 QtMultimedia，不需要额外安装 PortAudio 等系统库）。

使用 pull 模式：QAudioSource.start() 返回内部 QIODevice，
通过 readyRead 信号 + QTimer 双重保障读取数据。
兼容 macOS 上 PySide6 不正确调用自定义 QIODevice.writeData 的问题。
"""

import io
import struct
import wave

from PySide6.QtCore import QObject, QTimer, Signal, Slot

try:
    from PySide6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False


class AudioRecorder(QObject):
    """从默认麦克风录制音频，返回 WAV 格式字节。

    录制期间可通过 ``peak_level()`` / ``data_size()`` 获取实时状态。
    """

    error = Signal(str)

    _POLL_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._io_device = None
        self._poll_timer = None
        self._data = bytearray()
        self._peak = 0.0
        self._recording = False
        self._fmt = None

    @staticmethod
    def is_available():
        if not _HAS_MULTIMEDIA:
            return False
        try:
            return not QMediaDevices.defaultAudioInput().isNull()
        except Exception:
            return False

    @property
    def is_recording(self):
        return self._recording

    def start(self):
        if not _HAS_MULTIMEDIA:
            self.error.emit("当前环境缺少 QtMultimedia 模块，无法使用语音输入。")
            return False

        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self.error.emit("没有检测到麦克风，请检查音频设备。")
            return False

        fmt = self._negotiate_format(device)
        if fmt is None:
            self.error.emit("麦克风不支持所需的音频格式。")
            return False

        self._fmt = fmt
        self._data = bytearray()
        self._peak = 0.0

        self._source = QAudioSource(device, fmt, self)
        self._io_device = self._source.start()

        if self._io_device is None:
            self.error.emit("无法启动麦克风录音。")
            self._cleanup()
            return False

        # 双重保障：readyRead 信号 + 定时轮询
        self._io_device.readyRead.connect(self._on_ready_read)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_ready_read)
        self._poll_timer.start()

        self._recording = True
        return True

    def stop(self):
        """停止录音，返回 WAV 格式的 bytes。"""
        if not self._recording or self._source is None:
            return b""

        self._stop_poll()
        self._drain_remaining()
        self._source.stop()
        self._recording = False

        raw = bytes(self._data)
        wav_data = self._pcm_to_wav(raw) if raw else b""
        self._cleanup()
        return wav_data

    def cancel(self):
        """取消录音，不返回数据。"""
        if self._recording and self._source:
            self._stop_poll()
            self._source.stop()
        self._recording = False
        self._cleanup()

    def peak_level(self):
        """当前音频峰值（0.0–1.0），录音期间定时调用以驱动可视化。"""
        if self._recording:
            p = self._peak
            self._peak = 0.0
            return p
        return 0.0

    def data_size(self):
        """已录制的原始 PCM 数据大小（字节）。"""
        return len(self._data)

    def format_info(self):
        """当前录音格式描述，用于调试。"""
        if self._fmt is None:
            return "N/A"
        return "%dHz %dch %dbit" % (
            self._fmt.sampleRate(),
            self._fmt.channelCount(),
            self._fmt.bytesPerSample() * 8,
        )

    # ------------------------------------------------------------------

    @Slot()
    def _on_ready_read(self):
        """从内部 QIODevice 读取所有可用的音频数据。"""
        if self._io_device is None:
            return
        chunk = self._io_device.readAll()
        if chunk and len(chunk) > 0:
            # PySide6 readAll() 返回 QByteArray，转成 bytes
            raw = bytes(chunk)
            self._data.extend(raw)
            self._update_peak(raw)

    def _drain_remaining(self):
        """停止前读取残留数据。"""
        if self._io_device is None:
            return
        for _ in range(10):
            chunk = self._io_device.readAll()
            if chunk and len(chunk) > 0:
                self._data.extend(bytes(chunk))
            else:
                break

    def _update_peak(self, chunk):
        n_samples = len(chunk) // 2
        if n_samples == 0:
            return
        try:
            samples = struct.unpack("<%dh" % n_samples, chunk[: n_samples * 2])
            peak = max(abs(s) for s in samples) / 32768.0
            if peak > self._peak:
                self._peak = peak
        except struct.error:
            pass

    def _stop_poll(self):
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None
        if self._io_device is not None:
            try:
                self._io_device.readyRead.disconnect(self._on_ready_read)
            except (RuntimeError, TypeError):
                pass

    @staticmethod
    def _negotiate_format(device):
        """尝试 Int16 格式的几种常见采样率，返回设备支持的第一个。"""
        for rate in (16000, 44100, 48000):
            fmt = QAudioFormat()
            fmt.setSampleRate(rate)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if device.isFormatSupported(fmt):
                return fmt
        for rate in (44100, 48000):
            fmt = QAudioFormat()
            fmt.setSampleRate(rate)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if device.isFormatSupported(fmt):
                return fmt
        return None

    def _pcm_to_wav(self, raw_pcm):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._fmt.channelCount())
            wf.setsampwidth(self._fmt.bytesPerSample())
            wf.setframerate(self._fmt.sampleRate())
            wf.writeframes(raw_pcm)
        return buf.getvalue()

    def _cleanup(self):
        self._stop_poll()
        if self._source is not None:
            self._source.deleteLater()
            self._source = None
        self._io_device = None
        self._data = bytearray()
