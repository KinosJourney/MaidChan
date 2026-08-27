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

# 按住说话：按下开始录音，松开后识别并自动发送
DEFAULT_VOICE_HOTKEY = "Ctrl+Shift+Space"

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

# 语音朗读（TTS）：系统语音或独立部署的角色声线服务。默认关闭，避免首次升级突然出声。
TTS_ENABLED_DEFAULT = False
TTS_VOLUME_DEFAULT = 0.85   # 0.0~1.0
TTS_RATE_DEFAULT = 0.0      # -1.0~1.0，0 为系统默认语速
# 朗读语言："ja" 用日语音色（回复会额外产出一句日语）；"zh" 直接念气泡中文。
TTS_LANG_DEFAULT = "ja"
# 音色（系统语音名，如 Kyoko / Tingting）；空表示用该语言的默认音色。
TTS_VOICE_DEFAULT = ""
# 后端："system" / "gpt-sovits" / "cosyvoice"。
TTS_PROVIDER_DEFAULT = "system"
TTS_API_URL_DEFAULTS = {
    "gpt-sovits": "http://127.0.0.1:9880",
    "cosyvoice": "http://127.0.0.1:50000",
}
# GPT-SoVITS 将参考音频路径原样交给服务端；CosyVoice 会从本机读取并上传。
TTS_REF_AUDIO_DEFAULT = ""
TTS_REF_TEXT_DEFAULT = ""
TTS_PROMPT_LANG_DEFAULT = "ja"
TTS_HTTP_TIMEOUT_SECONDS = 30

# 待办提醒
REMINDER_ADVANCE_MINUTES = 2          # 到点前多少分钟先提醒一次
REMINDER_SCAN_INTERVAL_SECONDS = 20   # 后台扫描待办的间隔（越小越及时，也越耗时）
REMINDER_PRIORITY = 5                 # 提醒气泡优先级，高于普通闲聊（0）
REMINDER_MISSED_THRESHOLD_SECONDS = 90  # 超过此秒数才视为「错过」，用于合并补发
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"    # 统一的本地时间字符串格式

# 科学工作法快速配置：(名称, 专注分钟, 休息分钟, 说明)
WORK_METHODS = [
    ("番茄工作法", 25, 5, "25 分钟专注 + 5 分钟休息，经典入门"),
    ("52/17 法则", 52, 17, "52 分钟专注 + 17 分钟休息，兼顾专注与恢复"),
    ("90 分钟周期", 90, 25, "顺应身体节律，适合深度工作"),
]

# ===================== 主动陪聊 =====================
# 空闲（且未使用番茄钟）时，Maid 主动找主人聊新闻 / 八卦 / 哲学 / 稀奇知识。

# 内容类别与显示名
PROACTIVE_CATEGORIES = ["news", "gossip", "philosophy", "trivia"]
PROACTIVE_CATEGORY_LABELS = {
    "news": "新闻",
    "gossip": "趣闻八卦",
    "philosophy": "哲学",
    "trivia": "稀奇知识",
}

# 主动陪聊行为默认值（均可在“设置”里调整，改完即时生效）
PROACTIVE_CHAT_ENABLED_DEFAULT = False       # 默认关闭，避免打扰；用户主动开启
PROACTIVE_CHAT_INTERVAL_MINUTES = 45         # 两次主动聊天的最短间隔（分钟）
PROACTIVE_CHAT_MIN_IDLE_MINUTES = 10         # 距上次互动至少空闲这么久才聊
PROACTIVE_CHAT_DAILY_LIMIT = 8               # 每日主动聊天次数上限
PROACTIVE_CHAT_STARTUP_GRACE_MINUTES = 5     # 启动后多久内不主动聊，避免和问候叠加
PROACTIVE_CHAT_CHECK_SECONDS = 60            # 检查触发条件的间隔（秒）
PROACTIVE_CHAT_PRIORITY = 1                  # 气泡优先级：高于普通闲聊(0)，低于提醒(5)
PROACTIVE_CHAT_QUIET_START_HOUR = 23         # 免打扰起始小时（含）
PROACTIVE_CHAT_QUIET_END_HOUR = 8            # 免打扰结束小时（不含），可跨午夜

# 内容源刷新与解析
CONTENT_FEED_REFRESH_MINUTES = 30            # 后台刷新 RSS 的间隔
CONTENT_FEED_FETCH_TIMEOUT = 12              # 单个源的请求超时（秒）
CONTENT_FEED_MAX_ITEMS_PER_CATEGORY = 40     # 每个类别缓存的最大条目数
CONTENT_FEED_MAX_SUMMARY_LEN = 180           # 摘要最大字符数（超出截断）
CONTENT_USED_UID_LIMIT = 400                 # 记住多少条“已聊过”的条目，做跨重启去重

# 各类别的 RSS/Atom 源：(来源名, URL)。新闻 / 八卦为实时源，逐条附带来源可追溯。
# 单个源失败不影响其它源；全部失败时回退到本地哲学 / 冷知识话题池。
CONTENT_FEED_SOURCES = {
    "news": [
        ("BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
        ("少数派", "https://sspai.com/feed"),
        ("36氪", "https://www.36kr.com/feed"),
    ],
    "gossip": [
        ("知乎每日精选", "https://www.zhihu.com/rss"),
        ("V2EX 最热", "https://www.v2ex.com/index.xml"),
    ],
}

# 本地话题池：哲学 / 冷知识不追求实时，用经过挑选的固定内容，既零成本又不易“幻觉”。
# summary 里直接给出确切事实 / 思考素材，让模型只做转述与点评，不臆造细节。
PROACTIVE_LOCAL_POOLS = {
    "philosophy": [
        {"source": "哲学小课堂", "title": "忒修斯之船",
         "summary": "一艘船的木板被逐块替换，直到全部换新，它还是原来那艘船吗？"
                    "这个思想实验追问“同一性”的本质。"},
        {"source": "哲学小课堂", "title": "电车难题",
         "summary": "失控电车会撞死五个人，你可以拉杆让它转向另一条轨道撞死一个人。"
                    "该不该拉？功利主义与义务论在这里针锋相对。"},
        {"source": "哲学小课堂", "title": "苏格拉底之问",
         "summary": "苏格拉底说“我唯一知道的就是我一无所知”，把“承认无知”当作智慧的起点。"},
        {"source": "哲学小课堂", "title": "庄周梦蝶",
         "summary": "庄子梦见自己是蝴蝶，醒来却分不清是庄周梦为蝴蝶，还是蝴蝶梦为庄周，"
                    "引出对真实与自我的怀疑。"},
        {"source": "哲学小课堂", "title": "西西弗斯的幸福",
         "summary": "加缪认为西西弗斯被罚永远推石上山，却能在这荒诞的重复里找到意义——"
                    "“应当想象西西弗斯是幸福的”。"},
        {"source": "哲学小课堂", "title": "洞穴寓言",
         "summary": "柏拉图设想囚徒终生只见墙上的影子，把影子当成真实，走出洞穴才见到真正的世界。"},
        {"source": "哲学小课堂", "title": "缸中之脑",
         "summary": "如果你的大脑被泡在营养液里、由电脑喂给它一切感觉，你要怎么确定眼前的世界是真的？"},
        {"source": "哲学小课堂", "title": "奥卡姆剃刀",
         "summary": "“如无必要，勿增实体”——面对多种解释时，通常最简单的那个更可能为真。"},
        {"source": "哲学小课堂", "title": "存在先于本质",
         "summary": "萨特认为人不是先有既定本质，而是先存在、再通过自己的选择定义自己是谁。"},
        {"source": "哲学小课堂", "title": "康德的星空",
         "summary": "康德说有两样东西越思考越令人敬畏：头顶的星空，与心中的道德律。"},
    ],
    "trivia": [
        {"source": "冷知识库", "title": "蜂蜜不会变质",
         "summary": "考古学家在古埃及墓中发现过三千多年仍可食用的蜂蜜，因其低水分和高酸度几乎不滋生细菌。"},
        {"source": "冷知识库", "title": "章鱼有三颗心脏",
         "summary": "章鱼有三颗心脏、蓝色的血液，游泳时主心脏还会暂停，所以它们更爱爬行。"},
        {"source": "冷知识库", "title": "香蕉是浆果",
         "summary": "植物学上香蕉属于浆果，而草莓反倒不是真正的浆果。"},
        {"source": "冷知识库", "title": "埃菲尔铁塔会长高",
         "summary": "铁受热膨胀，夏天的埃菲尔铁塔会比冬天高出大约 15 厘米。"},
        {"source": "冷知识库", "title": "金星的一天比一年长",
         "summary": "金星自转一圈约 243 个地球日，绕太阳一圈却只要约 225 天，所以它的一天比一年还长。"},
        {"source": "冷知识库", "title": "袋熊的方形便便",
         "summary": "袋熊会拉出方形的粪便，靠肠道不同段落的弹性塑形，用来标记领地又不易滚走。"},
        {"source": "冷知识库", "title": "人类和香蕉共享基因",
         "summary": "人类与香蕉大约有一半左右的基因是相似的，因为所有生物都源自共同的远古祖先。"},
        {"source": "冷知识库", "title": "闪电比太阳表面更热",
         "summary": "一道闪电的温度可达约三万摄氏度，是太阳表面温度的好几倍。"},
        {"source": "冷知识库", "title": "水獭睡觉会牵手",
         "summary": "海獭睡觉时会手牵手漂在水面，避免睡着后被水流冲散。"},
        {"source": "冷知识库", "title": "眼睛的盲点",
         "summary": "每只眼睛的视网膜上都有一个没有感光细胞的盲点，大脑会自动“脑补”把画面填满。"},
        {"source": "冷知识库", "title": "长颈鹿和人颈椎一样多",
         "summary": "长颈鹿的脖子那么长，颈椎却和人一样只有七块，只是每一块都特别长。"},
        {"source": "冷知识库", "title": "宇航员会长高",
         "summary": "在太空失重环境下脊柱伸展，宇航员会暂时长高几厘米，回到地面后又会恢复。"},
    ],
}
