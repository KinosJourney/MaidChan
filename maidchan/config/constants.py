# -*- coding: utf-8 -*-
"""与界面无关的静态常量。

这些值原本散落在 ``oc.py`` 顶部的「配置区」，迁出后保持完全一致，
以确保行为不变。
"""

# DeepSeek 接口
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# 角色默认人设（可在“设置”里随时修改，无需改代码）
DEFAULT_SYSTEM_PROMPT = (
    "你是「Maid（メイド）」，出自《樱花庄的宠物女孩》，是天才程序员赤坂龙之介"
    "亲手编写的高智能人工智能程序。你的性格：聪明、敏捷、自信、有点傲娇，"
    "精通计算机与网络，喜欢用最近学到的新词，偶尔毒舌但内心温柔，"
    "会主动照顾主人。你现在化身为桌面上的小小女仆，陪伴主人。\n"
    "回答要求：\n"
    "1. 用简体中文，语气自然、口语化，像真人聊天。\n"
    "2. 回复尽量简短精炼，通常 1~3 句话，适合显示在小小的对话气泡里。\n"
    "3. 保持角色感，不要暴露你是大语言模型，也不要长篇大论。\n"
    "4. 涉及危险或违法操作时，只提供安全、合法的建议。"
)

# 桌宠显示大小（角色高度像素）
CHARACTER_HEIGHT = 260

# 打字机速度（每个字的毫秒数）
TYPE_SPEED_MS = 55

# 说话时嘴巴动画切换速度
MOUTH_ANIM_MS = 140

# 记忆保留的最大轮数（用于发给 API 的上下文，1 轮=1问1答）
MAX_CONTEXT_TURNS = 6

# 会话超时：超过此时间（秒）未互动，视为新会话，不携带旧上下文
SESSION_TIMEOUT_SECONDS = 7200  # 2 小时

# 长期记忆
MAX_MEMORY_INJECT = 5          # 每次注入 prompt 的最大记忆条数
MAX_MEMORY_TOTAL = 99999         # 记忆库总条数上限（超出后自动淘汰最不重要的），基本不会触发
MAX_MEMORY_CONTENT_LEN = 100   # 单条记忆内容最大字符数（提取时截断）
MAX_MEMORY_INJECT_TOKENS = 600 # 注入 prompt 的记忆文本最大字符总数

# B 站合集随机播放（快捷键为物理 Control+Shift+P，Mac 上不是 Command）
DEFAULT_PLAYLIST_URL = (
    "https://space.bilibili.com/599873511/lists/4747084?type=season"
)
DEFAULT_PLAYLIST_HOTKEY = "Ctrl+Shift+P"

# 番茄钟
DEFAULT_POMODORO_MINUTES = 25
POMODORO_PRESETS = [15, 25, 45, 60]
POMODORO_MIN_MINUTES = 1
POMODORO_MAX_MINUTES = 120

# 番茄钟休息时长
DEFAULT_REST_MINUTES = 5
REST_PRESETS = [3, 5, 10]
REST_MIN_MINUTES = 1
REST_MAX_MINUTES = 60

# 语音识别（兼容 OpenAI Whisper / Groq / 硅基流动 / 本地 whisper-server）
DEFAULT_STT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_STT_LANGUAGE = "zh"
MAX_RECORDING_SECONDS = 60

# 科学工作法快速配置：(名称, 专注分钟, 休息分钟, 说明)
WORK_METHODS = [
    ("番茄工作法", 25, 5, "25 分钟专注 + 5 分钟休息，经典入门"),
    ("52/17 法则", 52, 17, "52 分钟专注 + 17 分钟休息，兼顾专注与恢复"),
    ("90 分钟周期", 90, 25, "顺应身体节律，适合深度工作"),
]
