# -*- coding: utf-8 -*-
"""语音识别：发送录音到 OpenAI 兼容的 Whisper API，返回文本。

支持 OpenAI、Groq、硅基流动、本地 whisper-server 等兼容
``/v1/audio/transcriptions`` 接口的服务。
"""

import io
import os
import struct
import wave

from PySide6.QtCore import QThread, Signal

from ..config.paths import app_base_dir, env_file_candidates

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    requests = None
    HTTPAdapter = None


# 复用连接池，避免每次请求重新建立 TCP/TLS
_session = None


def _get_session():
    global _session
    if _session is None and requests is not None:
        _session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=2)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def _read_env_file():
    """读取 .env 文件，返回 {name: value} 字典。"""
    result = {}
    for env_path in env_file_candidates(app_base_dir()):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    name, sep, value = line.strip().partition("=")
                    if sep and name.strip():
                        result[name.strip()] = value.strip().strip("\"'")
            break
        except OSError:
            continue
    return result


def get_stt_env_config():
    """从环境变量和 .env 读取 STT 配置，返回 (api_key, base_url, model)。

    优先级：环境变量 > .env > 空字符串（由调用方用 Settings 默认值兜底）。
    """
    api_key = os.environ.get("STT_API_KEY", "").strip()
    base_url = os.environ.get("STT_BASE_URL", "").strip()
    model = os.environ.get("STT_MODEL", "").strip()

    if not (api_key and base_url and model):
        env = _read_env_file()
        if not api_key:
            api_key = env.get("STT_API_KEY", "")
        if not base_url:
            base_url = env.get("STT_BASE_URL", "")
        if not model:
            model = env.get("STT_MODEL", "")

    return api_key, base_url, model


def _downsample_wav(wav_data, target_rate=16000):
    """将 WAV 降采样到 16kHz mono，减小上传体积加快传输。

    如果已经是 16kHz mono 则直接返回。对非整数倍采样率做简单抽取。
    """
    try:
        src = io.BytesIO(wav_data)
        with wave.open(src, "rb") as wf:
            src_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())

        if src_rate == target_rate and n_channels == 1:
            return wav_data

        # 转为 mono
        if n_channels == 2 and sampwidth == 2:
            n = len(frames) // 4
            stereo = struct.unpack("<%dh" % (n * 2), frames[: n * 4])
            mono = [(stereo[i * 2] + stereo[i * 2 + 1]) // 2 for i in range(n)]
        elif sampwidth == 2:
            mono = list(struct.unpack("<%dh" % (len(frames) // 2), frames))
        else:
            return wav_data

        # 降采样（简单抽取）
        if src_rate != target_rate:
            ratio = src_rate / target_rate
            out = [mono[int(i * ratio)] for i in range(int(len(mono) / ratio))]
        else:
            out = mono

        raw = struct.pack("<%dh" % len(out), *out)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(target_rate)
            wf.writeframes(raw)
        return buf.getvalue()
    except Exception:
        return wav_data


class SpeechRecognizeWorker(QThread):
    """后台线程：将 WAV 音频发送到 Whisper API 进行转写。"""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, wav_data, base_url, api_key, model, language, parent=None):
        super().__init__(parent)
        self.wav_data = wav_data
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.language = language

    def run(self):
        if requests is None:
            self.failed.emit("缺少 requests 库，请先运行 install 脚本安装依赖。")
            return

        if not self.api_key:
            self.failed.emit(
                "未配置语音识别 API Key。\n"
                "请在「设置」中填写，或在 .env 文件中添加 STT_API_KEY=你的Key"
            )
            return

        if len(self.wav_data) < 5000:
            self.failed.emit("录音太短了，请再说一次～")
            return

        # 降采样到 16kHz mono 减小上传体积
        wav_data = _downsample_wav(self.wav_data, 16000)

        url = self.base_url + "/audio/transcriptions"
        headers = {"Authorization": "Bearer " + self.api_key}
        files = {
            "file": ("recording.wav", wav_data, "audio/wav"),
            "model": (None, self.model),
        }
        if self.language:
            files["language"] = (None, self.language)

        try:
            session = _get_session()
            resp = session.post(
                url, headers=headers, files=files, timeout=(5, 20),
            )
            if resp.status_code == 401:
                self.failed.emit("语音识别 API Key 无效（401），请检查配置。")
                return
            if resp.status_code == 402:
                self.failed.emit("语音识别账户余额不足（402），请充值。")
                return
            if resp.status_code != 200:
                self.failed.emit(
                    "语音识别失败 %s：%s" % (resp.status_code, resp.text[:120])
                )
                return

            text = self._extract_text(resp)
            if not text:
                self.failed.emit("没有识别到语音内容，请再说一次～")
                return
            self.finished_ok.emit(text)

        except requests.exceptions.Timeout:
            self.failed.emit("语音识别超时，请稍后再试～")
        except requests.exceptions.ConnectionError:
            self.failed.emit("无法连接语音识别服务，请检查网络。")
        except Exception as e:
            self.failed.emit("语音识别出错：%s" % str(e)[:150])

    @staticmethod
    def _extract_text(resp):
        """从响应中提取文本，兼容 JSON 和纯文本两种格式。"""
        try:
            data = resp.json()
            if isinstance(data, dict) and "text" in data:
                return data["text"].strip()
        except Exception:
            pass
        return resp.text.strip()
