# -*- coding: utf-8 -*-
"""语音输入模块测试：.env 解析、配置优先级、Worker API 调用逻辑。

Worker 测试通过 mock requests 实现，不会真正调用远程 API。
"""

import os
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import requests as real_requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=REPO_ROOT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ============================================================
#  _read_env_file / get_stt_env_config
# ============================================================


class ReadEnvFileTest(TempDirTestCase):
    def _write_env(self, content):
        path = os.path.join(self.tmp, ".env")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_reads_all_stt_vars(self):
        self._write_env(
            "DEEPSEEK_API_KEY=sk-deep\n"
            "STT_API_KEY=sk-stt\n"
            "STT_BASE_URL=https://api.siliconflow.cn/v1\n"
            "STT_MODEL=FunAudioLLM/SenseVoiceSmall\n"
        )
        from maidchan.audio.recognizer import _read_env_file

        with patch("maidchan.audio.recognizer.app_base_dir", return_value=self.tmp):
            result = _read_env_file()
        self.assertEqual(result["STT_API_KEY"], "sk-stt")
        self.assertEqual(result["STT_BASE_URL"], "https://api.siliconflow.cn/v1")
        self.assertEqual(result["STT_MODEL"], "FunAudioLLM/SenseVoiceSmall")

    def test_strips_quotes(self):
        self._write_env('STT_API_KEY="sk-quoted"\n')
        from maidchan.audio.recognizer import _read_env_file

        with patch("maidchan.audio.recognizer.app_base_dir", return_value=self.tmp):
            result = _read_env_file()
        self.assertEqual(result["STT_API_KEY"], "sk-quoted")

    def test_missing_file_returns_empty(self):
        from maidchan.audio.recognizer import _read_env_file

        fake_dir = os.path.join(self.tmp, "nonexistent")
        with patch("maidchan.audio.recognizer.app_base_dir", return_value=fake_dir):
            result = _read_env_file()
        self.assertEqual(result, {})

    def test_ignores_blank_and_comment_lines(self):
        self._write_env(
            "# 注释\n"
            "\n"
            "STT_API_KEY=valid\n"
            "   \n"
        )
        from maidchan.audio.recognizer import _read_env_file

        with patch("maidchan.audio.recognizer.app_base_dir", return_value=self.tmp):
            result = _read_env_file()
        self.assertEqual(result.get("STT_API_KEY"), "valid")
        self.assertNotIn("#", "".join(result.keys()))


class GetSttEnvConfigTest(TempDirTestCase):
    def tearDown(self):
        super().tearDown()
        for key in ("STT_API_KEY", "STT_BASE_URL", "STT_MODEL"):
            os.environ.pop(key, None)

    def test_reads_from_env_vars(self):
        from maidchan.audio.recognizer import get_stt_env_config

        with patch.dict(os.environ, {
            "STT_API_KEY": "env-key",
            "STT_BASE_URL": "https://env-url",
            "STT_MODEL": "env-model",
        }):
            key, url, model = get_stt_env_config()
        self.assertEqual(key, "env-key")
        self.assertEqual(url, "https://env-url")
        self.assertEqual(model, "env-model")

    def test_env_var_overrides_dotenv(self):
        env_path = os.path.join(self.tmp, ".env")
        with open(env_path, "w") as f:
            f.write("STT_API_KEY=file-key\nSTT_BASE_URL=https://file-url\nSTT_MODEL=file-model\n")

        from maidchan.audio.recognizer import get_stt_env_config

        with patch("maidchan.audio.recognizer.app_base_dir", return_value=self.tmp):
            with patch.dict(os.environ, {"STT_API_KEY": "env-key"}, clear=False):
                os.environ.pop("STT_BASE_URL", None)
                os.environ.pop("STT_MODEL", None)
                key, url, model = get_stt_env_config()

        self.assertEqual(key, "env-key")       # 环境变量优先
        self.assertEqual(url, "https://file-url")  # 回退到 .env
        self.assertEqual(model, "file-model")       # 回退到 .env

    def test_all_empty_returns_empty_strings(self):
        from maidchan.audio.recognizer import get_stt_env_config

        fake_dir = os.path.join(self.tmp, "nonexistent")
        with patch("maidchan.audio.recognizer.app_base_dir", return_value=fake_dir):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STT_API_KEY", None)
                os.environ.pop("STT_BASE_URL", None)
                os.environ.pop("STT_MODEL", None)
                key, url, model = get_stt_env_config()
        self.assertEqual((key, url, model), ("", "", ""))

    def test_reads_siliconflow_config(self):
        """模拟用户的真实 .env 配置。"""
        env_path = os.path.join(self.tmp, ".env")
        with open(env_path, "w") as f:
            f.write(
                "DEEPSEEK_API_KEY=sk-deep\n"
                "STT_API_KEY=sk-silicon\n"
                "STT_BASE_URL=https://api.siliconflow.cn/v1\n"
                "STT_MODEL=FunAudioLLM/SenseVoiceSmall\n"
            )

        from maidchan.audio.recognizer import get_stt_env_config

        with patch("maidchan.audio.recognizer.app_base_dir", return_value=self.tmp):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STT_API_KEY", None)
                os.environ.pop("STT_BASE_URL", None)
                os.environ.pop("STT_MODEL", None)
                key, url, model = get_stt_env_config()

        self.assertEqual(key, "sk-silicon")
        self.assertEqual(url, "https://api.siliconflow.cn/v1")
        self.assertEqual(model, "FunAudioLLM/SenseVoiceSmall")


# ============================================================
#  SpeechRecognizeWorker（mock requests，不实际联网）
# ============================================================


class SpeechRecognizeWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def _run_worker(self, wav_data=b"\x00" * 10000,
                    base_url="https://api.test.com/v1",
                    api_key="sk-test", model="whisper-1", language="zh"):
        from maidchan.audio.recognizer import SpeechRecognizeWorker

        worker = SpeechRecognizeWorker(
            wav_data, base_url, api_key, model, language,
        )
        results = {"ok": [], "fail": []}
        worker.finished_ok.connect(lambda t: results["ok"].append(t))
        worker.failed.connect(lambda t: results["fail"].append(t))
        worker.run()
        return results

    def _patch_session(self, mock_resp=None, side_effect=None):
        session = MagicMock()
        if side_effect is not None:
            session.post.side_effect = side_effect
        else:
            session.post.return_value = mock_resp
        return patch(
            "maidchan.audio.recognizer._get_session", return_value=session
        ), session

    # ---- URL 构建 ----

    def test_url_construction(self):
        mock_resp = MagicMock(status_code=200, text="你好世界")
        p, session = self._patch_session(mock_resp)
        with p:
            self._run_worker(base_url="https://api.siliconflow.cn/v1")

        url = session.post.call_args.args[0]
        self.assertEqual(url, "https://api.siliconflow.cn/v1/audio/transcriptions")

    def test_trailing_slash_stripped(self):
        mock_resp = MagicMock(status_code=200, text="ok")
        p, session = self._patch_session(mock_resp)
        with p:
            self._run_worker(base_url="https://api.test.com/v1/")

        url = session.post.call_args.args[0]
        self.assertEqual(url, "https://api.test.com/v1/audio/transcriptions")

    # ---- 成功路径 ----

    def test_success_plain_text(self):
        """OpenAI 返回纯文本的情况。"""
        mock_resp = MagicMock(status_code=200, text="  识别结果  \n")
        mock_resp.json.side_effect = ValueError("not json")
        p, _session = self._patch_session(mock_resp)
        with p:
            results = self._run_worker()

        self.assertEqual(results["ok"], ["识别结果"])
        self.assertEqual(results["fail"], [])

    def test_success_json_response(self):
        """硅基流动返回 JSON {"text": "..."} 的情况。"""
        mock_resp = MagicMock(status_code=200, text='{"text": "你好世界"}')
        mock_resp.json.return_value = {"text": "你好世界"}
        p, _session = self._patch_session(mock_resp)
        with p:
            results = self._run_worker()

        self.assertEqual(results["ok"], ["你好世界"])

    def test_model_passed_in_files(self):
        mock_resp = MagicMock(status_code=200, text="ok")
        mock_resp.json.side_effect = ValueError
        p, session = self._patch_session(mock_resp)
        with p:
            self._run_worker(model="FunAudioLLM/SenseVoiceSmall", language="zh")

        files = session.post.call_args.kwargs["files"]
        self.assertEqual(files["model"], (None, "FunAudioLLM/SenseVoiceSmall"))
        self.assertEqual(files["language"], (None, "zh"))

    def test_empty_language_not_sent(self):
        mock_resp = MagicMock(status_code=200, text="ok")
        mock_resp.json.side_effect = ValueError
        p, session = self._patch_session(mock_resp)
        with p:
            self._run_worker(language="")

        files = session.post.call_args.kwargs["files"]
        self.assertNotIn("language", files)

    # ---- 失败路径 ----

    def test_no_api_key(self):
        results = self._run_worker(api_key="")
        self.assertEqual(len(results["fail"]), 1)
        self.assertIn("API Key", results["fail"][0])

    def test_short_audio(self):
        results = self._run_worker(wav_data=b"\x00" * 100)
        self.assertEqual(len(results["fail"]), 1)
        self.assertIn("太短", results["fail"][0])

    def test_401_error(self):
        mock_resp = MagicMock(status_code=401)
        p, _session = self._patch_session(mock_resp)
        with p:
            results = self._run_worker()
        self.assertIn("401", results["fail"][0])

    def test_402_error(self):
        mock_resp = MagicMock(status_code=402)
        p, _session = self._patch_session(mock_resp)
        with p:
            results = self._run_worker()
        self.assertIn("余额不足", results["fail"][0])

    def test_500_error(self):
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        p, _session = self._patch_session(mock_resp)
        with p:
            results = self._run_worker()
        self.assertIn("500", results["fail"][0])

    def test_timeout(self):
        p, _session = self._patch_session(
            side_effect=real_requests.exceptions.Timeout(),
        )
        with p:
            results = self._run_worker()
        self.assertIn("超时", results["fail"][0])

    def test_connection_error(self):
        p, _session = self._patch_session(
            side_effect=real_requests.exceptions.ConnectionError(),
        )
        with p:
            results = self._run_worker()
        self.assertIn("网络", results["fail"][0])

    def test_empty_response(self):
        mock_resp = MagicMock(status_code=200, text="   ")
        mock_resp.json.return_value = {"text": ""}
        p, _session = self._patch_session(mock_resp)
        with p:
            results = self._run_worker()
        self.assertIn("没有识别到", results["fail"][0])

    def test_503_retries_then_succeeds(self):
        busy = MagicMock(status_code=503, text="Service Unavailable")
        ok = MagicMock(status_code=200, text="你好")
        ok.json.return_value = {"text": "你好"}
        p, session = self._patch_session(side_effect=[busy, ok])
        with p, patch("maidchan.audio.recognizer.time.sleep") as sleep:
            results = self._run_worker()
        self.assertEqual(results["ok"], ["你好"])
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(sleep.call_count, 1)

    def test_503_exhausted_shows_busy_message(self):
        busy = MagicMock(status_code=503, text="Service Unavailable")
        p, session = self._patch_session(side_effect=[busy, busy])
        with p, patch("maidchan.audio.recognizer.time.sleep"):
            results = self._run_worker()
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(len(results["fail"]), 1)
        self.assertIn("正忙", results["fail"][0])
        self.assertNotIn("503", results["fail"][0])

    def test_session_uses_system_proxy(self):
        """必须保留 trust_env=True：这台机器要经系统代理才能连通。"""
        from maidchan.audio.recognizer import _get_session

        session = _get_session()
        self.assertTrue(session.trust_env)
        session.close()

    def test_abort_suppresses_timeout_message(self):
        from maidchan.audio.recognizer import SpeechRecognizeWorker

        worker = SpeechRecognizeWorker(
            b"\x00" * 10000, "https://api.test.com/v1", "sk-test", "m", "zh",
        )
        results = {"ok": [], "fail": []}
        worker.finished_ok.connect(lambda t: results["ok"].append(t))
        worker.failed.connect(lambda t: results["fail"].append(t))
        worker.abort()
        p, session = self._patch_session(
            side_effect=real_requests.exceptions.Timeout(),
        )
        with p:
            worker.run()
        self.assertEqual(results["ok"], [])
        self.assertEqual(results["fail"], [])
        session.post.assert_not_called()


# ============================================================
#  录音格式协商 / PCM 转换
# ============================================================


class _FakeAudioDevice:
    """只报告固定采样率/声道，模拟 AirPods 等蓝牙麦。"""

    def __init__(self, rate, channels, sample_formats, preferred_sf=None):
        from PySide6.QtMultimedia import QAudioFormat

        self._rate = rate
        self._channels = channels
        self._sample_formats = set(sample_formats)
        self._preferred_sf = preferred_sf or QAudioFormat.SampleFormat.Float

    def preferredFormat(self):
        from PySide6.QtMultimedia import QAudioFormat

        fmt = QAudioFormat()
        fmt.setSampleRate(self._rate)
        fmt.setChannelCount(self._channels)
        fmt.setSampleFormat(self._preferred_sf)
        return fmt

    def isFormatSupported(self, fmt):
        return (
            fmt.sampleRate() == self._rate
            and fmt.channelCount() == self._channels
            and fmt.sampleFormat() in self._sample_formats
        )

    def minimumSampleRate(self):
        return self._rate

    def maximumSampleRate(self):
        return self._rate

    def minimumChannelCount(self):
        return self._channels

    def maximumChannelCount(self):
        return self._channels


class AudioFormatNegotiateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication

        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_airpods_24k_uses_native_int16(self):
        """蓝牙麦只支持 24kHz 时，应选设备原生采样率的 Int16，而不是报格式不支持。"""
        from PySide6.QtMultimedia import QAudioFormat
        from maidchan.audio.recorder import AudioRecorder

        device = _FakeAudioDevice(
            24000,
            1,
            {
                QAudioFormat.SampleFormat.Int16,
                QAudioFormat.SampleFormat.Float,
                QAudioFormat.SampleFormat.Int32,
                QAudioFormat.SampleFormat.UInt8,
            },
        )
        fmt = AudioRecorder._negotiate_format(device)
        self.assertIsNotNone(fmt)
        self.assertEqual(fmt.sampleRate(), 24000)
        self.assertEqual(fmt.channelCount(), 1)
        self.assertEqual(fmt.sampleFormat(), QAudioFormat.SampleFormat.Int16)

    def test_float_only_falls_back_to_preferred(self):
        from PySide6.QtMultimedia import QAudioFormat
        from maidchan.audio.recorder import AudioRecorder

        device = _FakeAudioDevice(
            48000, 2, {QAudioFormat.SampleFormat.Float},
        )
        fmt = AudioRecorder._negotiate_format(device)
        self.assertIsNotNone(fmt)
        self.assertEqual(fmt.sampleRate(), 48000)
        self.assertEqual(fmt.channelCount(), 2)
        self.assertEqual(fmt.sampleFormat(), QAudioFormat.SampleFormat.Float)

    def test_old_hardcoded_rates_are_not_required(self):
        """只支持 16k/44.1k/48k 之外的采样率时，旧逻辑会失败。"""
        from PySide6.QtMultimedia import QAudioFormat
        from maidchan.audio.recorder import AudioRecorder

        device = _FakeAudioDevice(
            24000, 1, {QAudioFormat.SampleFormat.Int16},
            preferred_sf=QAudioFormat.SampleFormat.Int16,
        )
        fmt = AudioRecorder._negotiate_format(device)
        self.assertEqual(fmt.sampleRate(), 24000)


class PcmToInt16Test(unittest.TestCase):
    def test_int16_passthrough(self):
        from maidchan.audio.recorder import _SF_INT16, _pcm_to_int16

        raw = struct.pack("<2h", 100, -100)
        self.assertEqual(_pcm_to_int16(raw, _SF_INT16), raw)

    def test_pyside_sample_format_enum(self):
        """Qt 的 SampleFormat 不能 int()，但录音回调会直接传入该枚举。"""
        from PySide6.QtMultimedia import QAudioFormat
        from maidchan.audio.recorder import _pcm_to_int16

        raw = struct.pack("<2h", 100, -100)
        self.assertEqual(
            _pcm_to_int16(raw, QAudioFormat.SampleFormat.Int16), raw
        )

    def test_float_to_int16(self):
        from maidchan.audio.recorder import _SF_FLOAT, _pcm_to_int16

        raw = struct.pack("<2f", 1.0, -1.0)
        out = _pcm_to_int16(raw, _SF_FLOAT)
        self.assertEqual(struct.unpack("<2h", out), (32767, -32767))

    def test_uint8_to_int16(self):
        from maidchan.audio.recorder import _SF_UINT8, _pcm_to_int16

        raw = bytes([128, 255, 0])
        out = _pcm_to_int16(raw, _SF_UINT8)
        self.assertEqual(struct.unpack("<3h", out), (0, 32512, -32768))


if __name__ == "__main__":
    unittest.main()

