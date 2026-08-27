# -*- coding: utf-8 -*-
"""语音合成（TTS）：统一系统语音与角色声线 Provider。

第一版使用 PySide6 自带的 ``QTextToSpeech``，走 macOS / Windows 系统语音引擎，
不依赖任何第三方库或云端 API。设计原则与 ``ChimePlayer`` 一致：引擎或中文语音
不可用时静默降级，绝不因语音失败阻断文字气泡等主流程。

``TtsPlayer`` 是稳定门面，具体实现由 ``TTSProvider`` 承担。
"""

import re

try:
    from PySide6.QtTextToSpeech import QTextToSpeech
except ImportError:  # 无 TTS 模块（旧版 PySide6 / 精简安装）时降级为无声
    QTextToSpeech = None

from PySide6.QtCore import QLocale, QObject

from ..config.constants import TTS_API_URL_DEFAULTS, TTS_PROVIDER_DEFAULT


# 主动陪聊等场景会在句尾附带 “（🔍 点我看原文·来源）” 之类的提示，朗读时应剥离。
_PAREN_LINK_RE = re.compile(r"[（(][^）)]*🔍[^）)]*[）)]")
_URL_RE = re.compile(r"https?://\S+")
_MARKDOWN_RE = re.compile(r"[`*_#>~|]")


def _is_symbol_or_emoji(ch):
    """判断字符是否为 emoji / 杂项符号（朗读时读不出或读得怪，直接剔除）。"""
    o = ord(ch)
    return (
        0x1F000 <= o <= 0x1FAFF     # emoji 主区
        or 0x2600 <= o <= 0x27BF    # 杂项符号与装饰符
        or 0x2B00 <= o <= 0x2BFF    # 杂项符号与箭头
        or o in (0x200D, 0xFE0E, 0xFE0F)  # 零宽连接符 / 变体选择符
    )


def sanitize_for_tts(text):
    """把气泡文本清洗成适合朗读的纯文本。

    去除链接提示、URL、常见 Markdown 记号与 emoji，避免系统语音把符号逐个念出。
    """
    if not text:
        return ""
    s = _PAREN_LINK_RE.sub("", text)
    s = _URL_RE.sub("", s)
    s = _MARKDOWN_RE.sub("", s)
    s = "".join(ch for ch in s if not _is_symbol_or_emoji(ch))
    # 合并多余空白（清洗后可能留下空格 / 空行）
    s = re.sub(r"\s+", " ", s)
    return s.strip()


class TTSProvider(QObject):
    """所有 TTS 后端遵循的最小接口。"""

    def is_available(self):
        raise NotImplementedError

    def available_voice_names(self, lang):
        return []

    def is_speaking(self):
        raise NotImplementedError

    def speak(self, text):
        raise NotImplementedError

    def preview(self, text, **settings):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def set_enabled(self, on):
        raise NotImplementedError

    def apply_settings(self, **settings):
        raise NotImplementedError

    def shutdown(self):
        raise NotImplementedError


class SystemTTSProvider(TTSProvider):
    """系统语音朗读器。

    参数：
        enabled: 是否启用朗读（关闭时完全不发声，也不占用引擎）。
        volume: 音量 0.0~1.0。
        rate: 语速 -1.0~1.0，0 为系统默认。
        lang: 朗读语言（"ja" / "zh"）。
        voice: 音色（QVoice.name()）；空表示用该语言的默认音色。
    """

    def __init__(self, parent=None, enabled=False, volume=0.85, rate=0.0,
                 lang="ja", voice=""):
        super().__init__(parent)
        self._enabled = bool(enabled)
        self._volume = volume
        self._rate = rate
        self._lang = lang or "ja"
        self._voice = voice or ""
        self._tts = None
        self._available = False
        # 语言 -> 该语言下选定的 QLocale / 可用音色列表（初始化时枚举一次）。
        self._locale_by_lang = {}
        self._voices_by_lang = {}

        if QTextToSpeech is None:
            return
        try:
            self._tts = QTextToSpeech(self)
            self._build_locale_map()
            self._ensure_locale(self._lang)
            self._tts.setVolume(volume)
            self._tts.setRate(rate)
            self._available = True
        except Exception:
            self._tts = None
            self._available = False

    # ---- 查询 ----
    def is_available(self):
        """系统是否具备可用的语音引擎。"""
        return self._available

    def available_voice_names(self, lang):
        """返回指定语言（"ja" / "zh"）下可用的音色名列表（去重、保序）。"""
        names = []
        for v in self._voices_by_lang.get(lang or "ja", []):
            try:
                name = v.name()
            except Exception:
                continue
            if name and name not in names:
                names.append(name)
        return names

    def is_speaking(self):
        if not self._tts:
            return False
        try:
            return self._tts.state() == QTextToSpeech.State.Speaking
        except Exception:
            try:
                return self._tts.state() == QTextToSpeech.Speaking
            except Exception:
                return False

    # ---- 朗读控制 ----
    def speak(self, text):
        """朗读一段文本；未启用 / 不可用 / 清洗后为空时静默跳过。"""
        if not (self._enabled and self._available and self._tts):
            return
        clean = sanitize_for_tts(text)
        if not clean:
            return
        try:
            self._ensure_locale(self._lang)  # 纠正可能被试听改动过的语言
            self._tts.stop()   # 打断上一段，避免多段语音叠加
            self._tts.say(clean)
        except Exception:
            pass

    def preview(self, text, volume=None, rate=None, lang=None, voice=None):
        """试听：忽略启用开关，用指定音量 / 语速 / 语言 / 音色临时念一句。"""
        if not (self._available and self._tts):
            return
        clean = sanitize_for_tts(text)
        if not clean:
            return
        try:
            if volume is not None:
                self._tts.setVolume(volume)
            if rate is not None:
                self._tts.setRate(rate)
            target_lang = lang if lang is not None else self._lang
            self._ensure_locale(target_lang)
            if voice is not None:
                self._set_voice_on(target_lang, voice)
            self._tts.stop()
            self._tts.say(clean)
        except Exception:
            pass

    def stop(self):
        if not self._tts:
            return
        try:
            self._tts.stop()
        except Exception:
            pass

    # ---- 设置 ----
    def set_enabled(self, on):
        self._enabled = bool(on)
        if not self._enabled:
            self.stop()

    def set_lang(self, lang):
        self._lang = lang or "ja"
        self._ensure_locale(self._lang)

    def set_voice(self, voice):
        self._voice = voice or ""
        self._ensure_locale(self._lang)  # 重新应用 locale + 音色

    def apply_settings(self, enabled=None, volume=None, rate=None, lang=None,
                       voice=None, **_config):
        """设置面板保存后调用，即时刷新开关 / 音量 / 语速 / 语言 / 音色。"""
        if enabled is not None:
            self.set_enabled(enabled)
        if volume is not None:
            self._volume = volume
            if self._tts:
                try:
                    self._tts.setVolume(volume)
                except Exception:
                    pass
        if rate is not None:
            self._rate = rate
            if self._tts:
                try:
                    self._tts.setRate(rate)
                except Exception:
                    pass
        # 语言与音色需一起应用：先切语言再选音色，避免音色被 locale 重置。
        if lang is not None:
            self._lang = lang or "ja"
        if voice is not None:
            self._voice = voice or ""
        if lang is not None or voice is not None:
            self._ensure_locale(self._lang)

    def shutdown(self):
        """应用退出时调用：立即停止朗读。"""
        self.stop()

    # ---- 内部 ----
    @staticmethod
    def _language_of(name):
        """取指定 BCP47 语言的 QLocale.language()，失败返回 None。"""
        try:
            return QLocale(name).language()
        except Exception:
            return None

    def _build_locale_map(self):
        """枚举系统语音，为「ja」「zh」各挑一个 locale（优先 ja_JP / zh_CN）。"""
        ja_lang = self._language_of("ja")
        zh_lang = self._language_of("zh")
        try:
            locales = list(self._tts.availableLocales())
        except Exception:
            locales = []

        def pick(lang_id, preferred):
            if lang_id is None:
                return None
            matches = [loc for loc in locales if loc.language() == lang_id]
            if not matches:
                return None
            return next(
                (loc for loc in matches if loc.name() == preferred),
                matches[0],
            )

        self._locale_by_lang = {
            "ja": pick(ja_lang, "ja_JP"),
            "zh": pick(zh_lang, "zh_CN"),
        }

        # 逐语言枚举可用音色（切到对应 locale 后读取 availableVoices）。
        self._voices_by_lang = {}
        for key, loc in self._locale_by_lang.items():
            voices = []
            if loc is not None:
                try:
                    self._tts.setLocale(loc)
                    voices = list(self._tts.availableVoices())
                except Exception:
                    voices = []
            self._voices_by_lang[key] = voices

    def _ensure_locale(self, lang):
        """把引擎切到指定语言的语音与音色；缺失时保留当前，不抛异常。"""
        if not self._tts:
            return
        loc = self._locale_by_lang.get(lang or "ja")
        if loc is not None:
            try:
                self._tts.setLocale(loc)
            except Exception:
                pass
        # locale 切换会把音色重置为默认，之后再套用用户选定的音色。
        if self._voice:
            self._set_voice_on(lang, self._voice)

    def _set_voice_on(self, lang, voice_name):
        """在指定语言的可用音色里按名字选中；找不到则保持默认。"""
        if not (self._tts and voice_name):
            return
        for v in self._voices_by_lang.get(lang or "ja", []):
            try:
                if v.name() == voice_name:
                    self._tts.setVoice(v)
                    return
            except Exception:
                continue


class TtsPlayer(QObject):
    """可热切换后端的 TTS 门面，保持原有调用接口不变。"""

    def __init__(self, parent=None, enabled=False, volume=0.85, rate=0.0,
                 lang="ja", voice="", provider=TTS_PROVIDER_DEFAULT,
                 api_url="", ref_audio="", ref_text="", prompt_lang="ja"):
        super().__init__(parent)
        self._provider_name = provider or TTS_PROVIDER_DEFAULT
        self._config = {
            "enabled": enabled,
            "volume": volume,
            "rate": rate,
            "lang": lang,
            "voice": voice,
            "api_url": api_url,
            "ref_audio": ref_audio,
            "ref_text": ref_text,
            "prompt_lang": prompt_lang,
        }
        self._provider = self._create_provider(
            self._provider_name, self._config, parent=self
        )
        self._preview_provider = None
        self._retired_providers = []

    @staticmethod
    def _create_provider(name, config, parent=None):
        if name == "gpt-sovits":
            from .neural_tts import GPTSoVITSProvider
            return GPTSoVITSProvider(parent, **config)
        if name == "cosyvoice":
            from .neural_tts import CosyVoiceProvider
            return CosyVoiceProvider(parent, **config)
        return SystemTTSProvider(parent, **{
            key: config[key]
            for key in ("enabled", "volume", "rate", "lang", "voice")
            if key in config
        })

    @property
    def provider_name(self):
        return self._provider_name

    def is_available(self):
        return self._provider.is_available()

    def available_voice_names(self, lang):
        return self._provider.available_voice_names(lang)

    def is_speaking(self):
        return self._provider.is_speaking()

    def speak(self, text):
        self._provider.speak(text)

    def preview(self, text, volume=None, rate=None, lang=None, voice=None,
                provider=None, api_url=None, ref_audio=None, ref_text=None,
                prompt_lang=None):
        preview_name = provider or self._provider_name
        config = dict(self._config)
        updates = {
            "enabled": True,
            "volume": volume,
            "rate": rate,
            "lang": lang,
            "voice": voice,
            "api_url": api_url,
            "ref_audio": ref_audio,
            "ref_text": ref_text,
            "prompt_lang": prompt_lang,
        }
        config.update({
            key: value for key, value in updates.items() if value is not None
        })
        if not config.get("api_url"):
            config["api_url"] = TTS_API_URL_DEFAULTS.get(preview_name, "")
        self.stop()
        if self._preview_provider is not None:
            self._retire_provider(self._preview_provider)
        self._preview_provider = self._create_provider(
            preview_name, config, parent=self
        )
        self._preview_provider.speak(text)

    def stop(self):
        self._provider.stop()
        if self._preview_provider is not None:
            self._preview_provider.stop()

    def set_enabled(self, on):
        self._config["enabled"] = bool(on)
        self._provider.set_enabled(on)

    def set_lang(self, lang):
        self._config["lang"] = lang
        if hasattr(self._provider, "set_lang"):
            self._provider.set_lang(lang)

    def set_voice(self, voice):
        self._config["voice"] = voice
        if hasattr(self._provider, "set_voice"):
            self._provider.set_voice(voice)

    def apply_settings(self, enabled=None, volume=None, rate=None, lang=None,
                       voice=None, provider=None, api_url=None, ref_audio=None,
                       ref_text=None, prompt_lang=None):
        updates = {
            "enabled": enabled,
            "volume": volume,
            "rate": rate,
            "lang": lang,
            "voice": voice,
            "api_url": api_url,
            "ref_audio": ref_audio,
            "ref_text": ref_text,
            "prompt_lang": prompt_lang,
        }
        self._config.update({
            key: value for key, value in updates.items() if value is not None
        })
        target = provider or self._provider_name
        if target != self._provider_name:
            old = self._provider
            self._retire_provider(old)
            self._provider_name = target
            self._provider = self._create_provider(
                target, self._config, parent=self
            )
        else:
            self._provider.apply_settings(**updates)

    def shutdown(self):
        self._provider.shutdown()
        if self._preview_provider is not None:
            self._preview_provider.shutdown()
            self._preview_provider = None
        for provider in list(self._retired_providers):
            provider.shutdown()
        self._retired_providers.clear()

    def _retire_provider(self, provider):
        """立即静音旧后端；未完成的 HTTP 请求结束后再销毁，避免卡住 UI。"""
        provider.stop()
        workers = getattr(provider, "_workers", None)
        if workers:
            self._retired_providers.append(provider)
            provider.idle.connect(
                lambda p=provider: self._dispose_retired_provider(p)
            )
        else:
            provider.deleteLater()

    def _dispose_retired_provider(self, provider):
        if provider not in self._retired_providers:
            return
        self._retired_providers.remove(provider)
        provider.shutdown()
        provider.deleteLater()

    def __getattr__(self, name):
        """兼容少量读取系统 Provider 内部状态的既有诊断代码。"""
        provider = self.__dict__.get("_provider")
        if provider is not None:
            return getattr(provider, name)
        raise AttributeError(name)
