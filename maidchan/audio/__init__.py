# -*- coding: utf-8 -*-
"""语音输入：录音 + 语音识别。"""

from .recorder import AudioRecorder
from .recognizer import SpeechRecognizeWorker, get_stt_env_config

__all__ = [
    "AudioRecorder",
    "SpeechRecognizeWorker",
    "get_stt_env_config",
]
