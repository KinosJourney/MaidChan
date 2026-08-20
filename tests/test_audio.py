# -*- coding: utf-8 -*-
"""语音输入模块测试：.env 解析、配置优先级、Worker API 调用逻辑。

Worker 测试通过 mock requests 实现，不会真正调用远程 API。
"""

import os
import shutil
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

    # ---- URL 构建 ----

    def test_url_construction(self):
        mock_resp = MagicMock(status_code=200, text="你好世界")
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            self._run_worker(base_url="https://api.siliconflow.cn/v1")

        url = mock_req.post.call_args.args[0]
        self.assertEqual(url, "https://api.siliconflow.cn/v1/audio/transcriptions")

    def test_trailing_slash_stripped(self):
        mock_resp = MagicMock(status_code=200, text="ok")
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            self._run_worker(base_url="https://api.test.com/v1/")

        url = mock_req.post.call_args.args[0]
        self.assertEqual(url, "https://api.test.com/v1/audio/transcriptions")

    # ---- 成功路径 ----

    def test_success_plain_text(self):
        """OpenAI 返回纯文本的情况。"""
        mock_resp = MagicMock(status_code=200, text="  识别结果  \n")
        mock_resp.json.side_effect = ValueError("not json")
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()

        self.assertEqual(results["ok"], ["识别结果"])
        self.assertEqual(results["fail"], [])

    def test_success_json_response(self):
        """硅基流动返回 JSON {"text": "..."} 的情况。"""
        mock_resp = MagicMock(status_code=200, text='{"text": "你好世界"}')
        mock_resp.json.return_value = {"text": "你好世界"}
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()

        self.assertEqual(results["ok"], ["你好世界"])

    def test_model_passed_in_files(self):
        mock_resp = MagicMock(status_code=200, text="ok")
        mock_resp.json.side_effect = ValueError
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            self._run_worker(model="FunAudioLLM/SenseVoiceSmall", language="zh")

        files = mock_req.post.call_args.kwargs["files"]
        self.assertEqual(files["model"], (None, "FunAudioLLM/SenseVoiceSmall"))
        self.assertEqual(files["language"], (None, "zh"))

    def test_empty_language_not_sent(self):
        mock_resp = MagicMock(status_code=200, text="ok")
        mock_resp.json.side_effect = ValueError
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            self._run_worker(language="")

        files = mock_req.post.call_args.kwargs["files"]
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
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()
        self.assertIn("401", results["fail"][0])

    def test_402_error(self):
        mock_resp = MagicMock(status_code=402)
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()
        self.assertIn("余额不足", results["fail"][0])

    def test_500_error(self):
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()
        self.assertIn("500", results["fail"][0])

    def test_timeout(self):
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.Timeout()
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()
        self.assertIn("超时", results["fail"][0])

    def test_connection_error(self):
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError()
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()
        self.assertIn("网络", results["fail"][0])

    def test_empty_response(self):
        mock_resp = MagicMock(status_code=200, text="   ")
        mock_resp.json.return_value = {"text": ""}
        with patch("maidchan.audio.recognizer.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = self._run_worker()
        self.assertIn("没有识别到", results["fail"][0])


if __name__ == "__main__":
    unittest.main()
