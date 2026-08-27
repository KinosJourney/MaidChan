# -*- coding: utf-8 -*-
"""语音输入：录音 + 语音识别。"""

from .recorder import AudioRecorder
from .recognizer import SpeechRecognizeWorker, get_stt_env_config
from .tts import SystemTTSProvider, TTSProvider, TtsPlayer, sanitize_for_tts
from .neural_tts import CosyVoiceProvider, GPTSoVITSProvider

__all__ = [
    "AudioRecorder",
    "SpeechRecognizeWorker",
    "get_stt_env_config",
    "TTSProvider",
    "SystemTTSProvider",
    "GPTSoVITSProvider",
    "CosyVoiceProvider",
    "TtsPlayer",
    "sanitize_for_tts",
]
