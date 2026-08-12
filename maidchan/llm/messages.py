# -*- coding: utf-8 -*-
"""把人设、档案与历史拼装成发送给 API 的 messages。"""

from ..config.constants import MAX_CONTEXT_TURNS


def build_chat_messages(system_prompt, profile, history, max_context_turns=MAX_CONTEXT_TURNS):
    """构造 OpenAI 格式的 messages 列表。

    等价于原 ``MaidPet._build_messages``：档案前缀 + 人设作为 system，
    再拼接最近若干轮历史。
    """
    prefix = profile.as_prompt_prefix()
    sys_content = prefix + system_prompt
    messages = [{"role": "system", "content": sys_content}]
    messages.extend(history.context_messages(max_context_turns))
    return messages
