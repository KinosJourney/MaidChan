# -*- coding: utf-8 -*-
"""语音朗读（TTS）测试：文本清洗、通知编排、降级安全。

TtsPlayer 的真实系统引擎行为不做断言（依赖运行环境），只验证：
清洗逻辑纯函数、NotificationManager 与 TTS 的编排、以及关闭 / 不可用时的安全降级。
"""

import unittest
from unittest.mock import MagicMock, mock_open, patch

from PySide6.QtCore import QCoreApplication

from maidchan.audio.neural_tts import (
    HttpSynthesisWorker,
    cosyvoice_form,
    gpt_sovits_payload,
)
from maidchan.audio.tts import (
    SystemTTSProvider,
    TTSProvider,
    TtsPlayer,
    sanitize_for_tts,
)
from maidchan.core.notifications import NotificationManager
from maidchan.ui.text_utils import split_display_and_speech


def _app():
    return QCoreApplication.instance() or QCoreApplication([])


class SanitizeTextTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(sanitize_for_tts(""), "")
        self.assertEqual(sanitize_for_tts(None), "")

    def test_strip_url(self):
        self.assertEqual(
            sanitize_for_tts("看这里 https://example.com/a?b=1 就懂了"),
            "看这里 就懂了",
        )

    def test_strip_link_hint(self):
        text = "今天有个大新闻哦（🔍 点我看原文·BBC）"
        self.assertEqual(sanitize_for_tts(text), "今天有个大新闻哦")

    def test_strip_emoji_and_markdown(self):
        self.assertEqual(sanitize_for_tts("**重点** 🍰 提醒你"), "重点 提醒你")

    def test_plain_text_unchanged(self):
        self.assertEqual(sanitize_for_tts("你好，主人。"), "你好，主人。")


class StubBubble:
    def __init__(self):
        self._visible = False
        self.spoken = []
        self.on_sentence_typing = None
        self.on_sentence_done = None
        self.on_all_done = None
        self.on_geometry_changed = None

    def isVisible(self):
        return self._visible

    def speak(self, sentences, link=None):
        self._visible = True
        self.spoken.append(sentences)


class StubState:
    def begin_speaking(self):
        pass

    def end_sentence(self):
        pass

    def end_speaking(self):
        pass


class StubTts:
    def __init__(self):
        self.spoken = []
        self.stops = 0
        self._speaking = False

    def speak(self, text):
        self.spoken.append(text)
        self._speaking = True

    def stop(self):
        self.stops += 1
        self._speaking = False

    def is_speaking(self):
        return self._speaking


class NotificationTtsTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.bubble = StubBubble()
        self.state = StubState()
        self.tts = StubTts()
        self.nm = NotificationManager(
            bubble=self.bubble,
            split_fn=lambda t: [t],
            position_cb=lambda: None,
            state_machine=self.state,
            tts=self.tts,
        )

    def test_speaks_japanese_when_speak_text_given(self):
        self.nm.show("你好呀", speak_text="こんにちは")
        self.assertEqual(self.tts.spoken, ["こんにちは"])

    def test_no_speak_text_stays_silent(self):
        # 纯中文本地提示（无日语朗读文本）不发声，但仍会打断上一段语音。
        self.nm.show("设置已保存")
        self.assertEqual(self.tts.spoken, [])
        self.assertGreaterEqual(self.tts.stops, 1)

    def test_all_done_does_not_cut_off_tts(self):
        self.nm.show("念一句", speak_text="ひとこと")
        stops_before = self.tts.stops
        self.bubble.on_all_done()
        self.assertEqual(self.tts.stops, stops_before)
        self.assertTrue(self.tts.is_speaking())

    def test_is_busy_reflects_tts(self):
        # 气泡不可见但语音仍在播放，也算忙。
        self.tts._speaking = True
        self.assertTrue(self.nm.is_busy())

    def test_low_priority_rejected_does_not_speak(self):
        self.nm.show("紧急", priority=5, speak_text="きんきゅう")
        self.tts.spoken.clear()
        self.nm.show("闲聊", priority=1, speak_text="ざつだん")  # 应被高优先级拦截
        self.assertEqual(self.tts.spoken, [])


class SplitDisplaySpeechTest(unittest.TestCase):
    def test_no_marker_returns_none_speech(self):
        display, speech = split_display_and_speech("你好，主人。")
        self.assertEqual(display, "你好，主人。")
        self.assertIsNone(speech)

    def test_splits_chinese_and_japanese(self):
        display, speech = split_display_and_speech(
            "早上好，主人！\n[JA] おはようございます、ご主人様！"
        )
        self.assertEqual(display, "早上好，主人！")
        self.assertEqual(speech, "おはようございます、ご主人様！")

    def test_marker_variants(self):
        display, speech = split_display_and_speech("在的哦【ja】はい、います")
        self.assertEqual(display, "在的哦")
        self.assertEqual(speech, "はい、います")

    def test_empty(self):
        self.assertEqual(split_display_and_speech(""), ("", None))


class TtsPlayerDegradeTest(unittest.TestCase):
    def setUp(self):
        _app()

    def test_disabled_player_is_silent(self):
        player = TtsPlayer(enabled=False)
        # 无论引擎是否可用，关闭时 speak 不应抛异常。
        player.speak("不应发声")
        self.assertIsInstance(player.is_available(), bool)
        self.assertFalse(player.is_speaking() and not player.is_available())

    def test_stop_and_shutdown_safe(self):
        player = TtsPlayer(enabled=False)
        player.stop()
        player.shutdown()

    def test_system_provider_is_default(self):
        player = TtsPlayer(enabled=False)
        self.assertIsInstance(player._provider, TTSProvider)
        self.assertIsInstance(player._provider, SystemTTSProvider)
        self.assertEqual(player.provider_name, "system")
        player.shutdown()

    def test_provider_can_be_switched(self):
        player = TtsPlayer(enabled=False)
        player.apply_settings(
            provider="gpt-sovits",
            api_url="http://127.0.0.1:9880",
            ref_audio="/server/reference.wav",
            ref_text="こんにちは",
        )
        self.assertEqual(player.provider_name, "gpt-sovits")
        player.shutdown()


class NeuralTtsRequestTest(unittest.TestCase):
    def test_gpt_sovits_official_payload(self):
        payload = gpt_sovits_payload("おはよう", {
            "lang": "ja",
            "ref_audio": "/voices/maid.wav",
            "ref_text": "こんにちは",
            "prompt_lang": "ja",
            "speed": 1.1,
        })
        self.assertEqual(payload["text"], "おはよう")
        self.assertEqual(payload["ref_audio_path"], "/voices/maid.wav")
        self.assertEqual(payload["speed_factor"], 1.1)
        self.assertEqual(payload["media_type"], "wav")
        self.assertFalse(payload["streaming_mode"])

    def test_cosyvoice_official_form(self):
        form = cosyvoice_form(
            "早上好", {"ref_text": "你好，主人", "speed": 0.9}
        )
        self.assertEqual(form, {
            "tts_text": "早上好",
            "prompt_text": "你好，主人",
            "speed": 0.9,
        })

    @patch("maidchan.audio.neural_tts.requests.post")
    def test_gpt_worker_posts_json_to_official_endpoint(self, mock_post):
        response = MagicMock()
        response.content = b"RIFFaudio"
        response.headers = {"content-type": "audio/wav"}
        mock_post.return_value = response
        worker = HttpSynthesisWorker("gpt-sovits", "こんにちは", {
            "api_url": "http://127.0.0.1:9880/",
            "lang": "ja",
            "ref_audio": "/voices/maid.wav",
            "ref_text": "おはよう",
            "prompt_lang": "ja",
        })
        emitted = []
        worker.synthesized.connect(lambda audio, suffix: emitted.append(
            (audio, suffix)
        ))
        worker.run()
        self.assertEqual(mock_post.call_args.args[0],
                         "http://127.0.0.1:9880/tts")
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["ref_audio_path"],
            "/voices/maid.wav",
        )
        self.assertEqual(emitted, [(b"RIFFaudio", ".wav")])

    @patch("maidchan.audio.neural_tts.requests.post")
    @patch("builtins.open", new_callable=mock_open, read_data=b"wave")
    def test_cosy_worker_uploads_prompt_wav(self, _mock_file, mock_post):
        response = MagicMock()
        response.content = b"RIFFaudio"
        response.headers = {"content-type": "audio/wav"}
        mock_post.return_value = response
        worker = HttpSynthesisWorker("cosyvoice", "早上好", {
            "api_url": "http://127.0.0.1:50000",
            "ref_audio": "/voices/maid.wav",
            "ref_text": "你好，主人",
        })
        worker.run()
        self.assertEqual(
            mock_post.call_args.args[0],
            "http://127.0.0.1:50000/inference_zero_shot",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["data"]["prompt_text"], "你好，主人"
        )
        self.assertEqual(
            mock_post.call_args.kwargs["files"]["prompt_wav"][0], "maid.wav"
        )


class TtsLangTest(unittest.TestCase):
    def setUp(self):
        _app()

    def test_lang_switch_selects_matching_locale(self):
        player = TtsPlayer(enabled=True, lang="ja")
        if not player.is_available():
            self.skipTest("系统无可用语音引擎")
        ja = player._locale_by_lang.get("ja")
        zh = player._locale_by_lang.get("zh")
        if ja is not None:
            player.set_lang("ja")
            self.assertTrue(player._tts.locale().name().startswith("ja"))
        if zh is not None:
            player.set_lang("zh")
            self.assertTrue(player._tts.locale().name().startswith("zh"))


if __name__ == "__main__":
    unittest.main()
