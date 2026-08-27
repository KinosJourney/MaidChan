# -*- coding: utf-8 -*-
"""通过独立 HTTP 服务合成并播放角色声线。"""

import os
import tempfile

import requests
from PySide6.QtCore import QObject, QThread, QUrl, Signal

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:
    QAudioOutput = None
    QMediaPlayer = None

from ..config.constants import TTS_HTTP_TIMEOUT_SECONDS


def _endpoint(base_url, path):
    base = (base_url or "").rstrip("/")
    return base if base.endswith(path) else base + path


def gpt_sovits_payload(text, config):
    """构造 GPT-SoVITS 官方 api_v2.py 的非流式请求。"""
    return {
        "text": text,
        "text_lang": config.get("lang", "ja"),
        "ref_audio_path": config.get("ref_audio", ""),
        "prompt_text": config.get("ref_text", ""),
        "prompt_lang": config.get("prompt_lang", "ja"),
        "speed_factor": config.get("speed", 1.0),
        "media_type": "wav",
        "streaming_mode": False,
    }


def cosyvoice_form(text, config):
    """构造 CosyVoice 官方 zero-shot FastAPI 的表单字段。"""
    return {
        "tts_text": text,
        "prompt_text": config.get("ref_text", ""),
        # 官方旧版会忽略额外表单字段，新版服务可直接使用该倍率。
        "speed": config.get("speed", 1.0),
    }


class HttpSynthesisWorker(QThread):
    """在线程中执行一次合成，避免阻塞 Qt 事件循环。"""

    synthesized = Signal(bytes, str)
    failed = Signal(str)

    def __init__(self, provider_name, text, config, parent=None):
        super().__init__(parent)
        self.provider_name = provider_name
        self.text = text
        self.config = dict(config)

    def run(self):
        try:
            timeout = float(self.config.get("timeout", TTS_HTTP_TIMEOUT_SECONDS))
            if self.provider_name == "gpt-sovits":
                response = requests.post(
                    _endpoint(self.config.get("api_url"), "/tts"),
                    json=gpt_sovits_payload(self.text, self.config),
                    timeout=timeout,
                )
            elif self.provider_name == "cosyvoice":
                ref_audio = self.config.get("ref_audio", "")
                with open(ref_audio, "rb") as audio_file:
                    response = requests.post(
                        _endpoint(
                            self.config.get("api_url"), "/inference_zero_shot"
                        ),
                        data=cosyvoice_form(self.text, self.config),
                        files={
                            "prompt_wav": (
                                os.path.basename(ref_audio),
                                audio_file,
                                "audio/wav",
                            )
                        },
                        timeout=timeout,
                    )
            else:
                raise ValueError("未知 TTS Provider")

            response.raise_for_status()
            audio = response.content
            if not audio:
                raise ValueError("TTS 服务返回了空音频")
            content_type = response.headers.get("content-type", "").lower()
            if "json" in content_type:
                raise ValueError("TTS 服务未返回音频")
            self.synthesized.emit(audio, ".wav")
        except Exception as exc:
            self.failed.emit(str(exc))


class NeuralTTSProvider(QObject):
    """神经网络 TTS Provider 公共实现：异步请求、打断与 WAV 播放。"""

    idle = Signal()
    provider_name = ""

    def __init__(self, parent=None, **config):
        super().__init__(parent)
        self._config = dict(config)
        self._enabled = bool(config.get("enabled", False))
        self._generation = 0
        self._synthesizing = False
        self._workers = set()
        self._audio_path = None
        self._player = None
        self._audio_output = None

        if QMediaPlayer is not None and QAudioOutput is not None:
            try:
                self._player = QMediaPlayer(self)
                self._audio_output = QAudioOutput(self)
                self._player.setAudioOutput(self._audio_output)
                self._set_volume(config.get("volume", 0.85))
                self._player.playbackStateChanged.connect(
                    self._on_playback_state_changed
                )
            except Exception:
                self._player = None
                self._audio_output = None

    def is_available(self):
        if self._player is None or not self._config.get("api_url"):
            return False
        if not self._config.get("ref_audio") or not self._config.get("ref_text"):
            return False
        if self.provider_name == "cosyvoice":
            return os.path.isfile(self._config["ref_audio"])
        return True

    def available_voice_names(self, _lang):
        return []

    def is_speaking(self):
        if self._synthesizing:
            return True
        if self._player is None:
            return False
        try:
            return (
                self._player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState
            )
        except Exception:
            return False

    def speak(self, text):
        from .tts import sanitize_for_tts

        clean = sanitize_for_tts(text)
        if not (self._enabled and self.is_available() and clean):
            return
        self.stop()
        sequence = self._generation
        config = dict(self._config)
        config["speed"] = self._speed_factor(config.get("rate", 0.0))
        worker = HttpSynthesisWorker(
            self.provider_name, clean, config, parent=self
        )
        worker.sequence = sequence
        self._workers.add(worker)
        self._synthesizing = True
        # 绑定到 QObject 方法，确保结果排队回到 Provider 所在的 UI 线程再操作播放器。
        worker.synthesized.connect(self._on_worker_synthesized)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def preview(self, text, **settings):
        old_enabled = self._enabled
        self._enabled = True
        self.apply_settings(**settings)
        self.speak(text)
        self._enabled = old_enabled

    def stop(self):
        self._generation += 1
        self._synthesizing = False
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        self._remove_audio_file()

    def set_enabled(self, on):
        self._enabled = bool(on)
        if not self._enabled:
            self.stop()

    def set_lang(self, lang):
        self._config["lang"] = lang or "ja"

    def set_voice(self, _voice):
        pass

    def apply_settings(self, enabled=None, volume=None, rate=None, lang=None,
                       **config):
        if enabled is not None:
            self.set_enabled(enabled)
        if volume is not None:
            self._config["volume"] = volume
            self._set_volume(volume)
        if rate is not None:
            self._config["rate"] = rate
        if lang is not None:
            self._config["lang"] = lang
        self._config.update({
            key: value for key, value in config.items() if value is not None
        })

    def shutdown(self):
        self.stop()
        for worker in list(self._workers):
            worker.requestInterruption()
            worker.wait(int(
                (float(self._config.get(
                    "timeout", TTS_HTTP_TIMEOUT_SECONDS
                )) + 1) * 1000
            ))
        self._workers.clear()

    @staticmethod
    def _speed_factor(rate):
        return round(max(0.5, min(1.5, 1.0 + float(rate) * 0.5)), 2)

    def _set_volume(self, volume):
        if self._audio_output is not None:
            try:
                self._audio_output.setVolume(
                    max(0.0, min(1.0, float(volume)))
                )
            except Exception:
                pass

    def _on_synthesized(self, worker, sequence, audio, suffix):
        if worker not in self._workers or sequence != self._generation:
            return
        self._synthesizing = False
        try:
            handle = tempfile.NamedTemporaryFile(
                prefix="maidchan_tts_", suffix=suffix, delete=False
            )
            with handle:
                handle.write(audio)
            self._audio_path = handle.name
            self._player.setSource(QUrl.fromLocalFile(self._audio_path))
            self._player.play()
        except Exception:
            self._remove_audio_file()

    def _on_worker_synthesized(self, audio, suffix):
        worker = self.sender()
        self._on_synthesized(
            worker, getattr(worker, "sequence", -1), audio, suffix
        )

    def _on_failed(self, worker, sequence):
        if worker in self._workers and sequence == self._generation:
            self._synthesizing = False

    def _on_worker_failed(self, _error):
        worker = self.sender()
        self._on_failed(worker, getattr(worker, "sequence", -1))

    def _discard_worker(self, worker):
        self._workers.discard(worker)
        worker.deleteLater()
        if not self._workers:
            self.idle.emit()

    def _on_worker_finished(self):
        self._discard_worker(self.sender())

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._remove_audio_file()

    def _remove_audio_file(self):
        path, self._audio_path = self._audio_path, None
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


class GPTSoVITSProvider(NeuralTTSProvider):
    provider_name = "gpt-sovits"


class CosyVoiceProvider(NeuralTTSProvider):
    provider_name = "cosyvoice"
