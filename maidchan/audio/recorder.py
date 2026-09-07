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
    QAudioFormat = None  # noqa: N816


# 与 QAudioFormat.SampleFormat 数值一致，转换函数不依赖 Qt 枚举。
_SF_UINT8 = 1
_SF_INT16 = 2
_SF_INT32 = 3
_SF_FLOAT = 4

_COMMON_RATES = (16000, 24000, 44100, 48000, 22050, 32000, 8000, 96000)


def _sample_format_id(sample_format):
    """把 Qt SampleFormat 或整数统一成 1/2/3/4。

    PySide6 的枚举不是 IntEnum，``int(SampleFormat.Int16)`` 会直接 TypeError。
    """
    if isinstance(sample_format, int):
        return sample_format
    value = getattr(sample_format, "value", None)
    if isinstance(value, int):
        return value
    try:
        return int(sample_format)
    except (TypeError, ValueError):
        return _SF_INT16


def _pcm_to_int16(raw, sample_format):
    """将原始 PCM 转为交错 Int16 小端字节。"""
    if not raw:
        return b""
    sf = _sample_format_id(sample_format)
    if sf == _SF_INT16:
        n = len(raw) - (len(raw) % 2)
        return raw[:n] if n != len(raw) else raw
    if sf == _SF_FLOAT:
        n = len(raw) // 4
        if n == 0:
            return b""
        values = struct.unpack("<%df" % n, raw[: n * 4])
        samples = [
            max(-32768, min(32767, int(v * 32767.0))) for v in values
        ]
        return struct.pack("<%dh" % n, *samples)
    if sf == _SF_INT32:
        n = len(raw) // 4
        if n == 0:
            return b""
        values = struct.unpack("<%di" % n, raw[: n * 4])
        samples = [max(-32768, min(32767, v >> 16)) for v in values]
        return struct.pack("<%dh" % n, *samples)
    if sf == _SF_UINT8:
        samples = [max(-32768, min(32767, (b - 128) << 8)) for b in raw]
        return struct.pack("<%dh" % len(samples), *samples)
    n = len(raw) - (len(raw) % 2)
    return raw[:n]


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
        self._pending = bytearray()
        self._peak = 0.0
        self._recording = False
        self._fmt = None
        self._frame_bytes = 2
        self._ready_connected = False

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
        self._pending = bytearray()
        self._peak = 0.0
        self._frame_bytes = max(1, fmt.bytesPerSample() * fmt.channelCount())

        self._source, self._io_device = self._open_source(device, fmt)
        if self._io_device is None:
            preferred = device.preferredFormat()
            if (
                preferred.isValid()
                and preferred.sampleRate() > 0
                and (
                    preferred.sampleRate() != fmt.sampleRate()
                    or preferred.channelCount() != fmt.channelCount()
                    or preferred.sampleFormat() != fmt.sampleFormat()
                )
            ):
                fmt = preferred
                self._fmt = fmt
                self._frame_bytes = max(
                    1, fmt.bytesPerSample() * fmt.channelCount()
                )
                self._source, self._io_device = self._open_source(device, fmt)

        if self._io_device is None:
            self.error.emit("无法启动麦克风录音。")
            self._cleanup()
            return False

        # 双重保障：readyRead 信号 + 定时轮询
        self._io_device.readyRead.connect(self._on_ready_read)
        self._ready_connected = True

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
        """已录制的 Int16 PCM 数据大小（字节）。"""
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

    def _open_source(self, device, fmt):
        source = QAudioSource(device, fmt, self)
        io_device = source.start()
        if io_device is None:
            source.deleteLater()
            return None, None
        return source, io_device

    @Slot()
    def _on_ready_read(self):
        """从内部 QIODevice 读取所有可用的音频数据。"""
        if self._io_device is None:
            return
        chunk = self._io_device.readAll()
        if chunk and len(chunk) > 0:
            self._append_capture(bytes(chunk))

    def _drain_remaining(self):
        """停止前读取残留数据。"""
        if self._io_device is None:
            return
        for _ in range(10):
            chunk = self._io_device.readAll()
            if chunk and len(chunk) > 0:
                self._append_capture(bytes(chunk))
            else:
                break

    def _append_capture(self, raw):
        """按帧对齐后转为 Int16，再写入缓冲区。"""
        if not raw or self._fmt is None:
            return
        self._pending.extend(raw)
        frame = self._frame_bytes
        n = (len(self._pending) // frame) * frame
        if n == 0:
            return
        complete = bytes(self._pending[:n])
        del self._pending[:n]
        pcm16 = _pcm_to_int16(complete, self._fmt.sampleFormat())
        if pcm16:
            self._data.extend(pcm16)
            self._update_peak(pcm16)

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
        if self._io_device is not None and getattr(self, "_ready_connected", False):
            self._ready_connected = False
            try:
                self._io_device.readyRead.disconnect(self._on_ready_read)
            except (RuntimeError, TypeError):
                pass

    @staticmethod
    def _make_format(rate, channels, sample_format):
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(sample_format)
        return fmt

    @staticmethod
    def _negotiate_format(device):
        """按设备真实能力选格式：优先 Int16，采样率跟麦克风走。

        AirPods 等蓝牙麦常见只支持 24kHz，不能只试 16k/44.1k/48k。
        """
        preferred = device.preferredFormat()
        pref_rate = preferred.sampleRate() if preferred.isValid() else 0
        pref_ch = preferred.channelCount() if preferred.isValid() else 0
        pref_sf = preferred.sampleFormat() if preferred.isValid() else None

        min_rate = device.minimumSampleRate() or 1
        max_rate = device.maximumSampleRate() or 192000
        min_ch = device.minimumChannelCount() or 1
        max_ch = device.maximumChannelCount() or 8

        rates = []
        if pref_rate > 0:
            rates.append(pref_rate)
        for rate in _COMMON_RATES:
            if rate not in rates:
                rates.append(rate)
        rates = [r for r in rates if min_rate <= r <= max_rate]

        channels = []
        if min_ch <= pref_ch <= max_ch:
            channels.append(pref_ch)
        for ch in (1, 2):
            if ch not in channels and min_ch <= ch <= max_ch:
                channels.append(ch)

        formats = [QAudioFormat.SampleFormat.Int16]
        if pref_sf is not None and pref_sf not in formats:
            formats.append(pref_sf)
        for sf in (
            QAudioFormat.SampleFormat.Float,
            QAudioFormat.SampleFormat.Int32,
            QAudioFormat.SampleFormat.UInt8,
        ):
            if sf not in formats:
                formats.append(sf)

        for sf in formats:
            for ch in channels:
                for rate in rates:
                    fmt = AudioRecorder._make_format(rate, ch, sf)
                    if device.isFormatSupported(fmt):
                        return fmt

        if preferred.isValid() and pref_rate > 0 and pref_ch > 0:
            return preferred
        return None

    def _pcm_to_wav(self, raw_pcm):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._fmt.channelCount())
            wf.setsampwidth(2)
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
        self._pending = bytearray()
