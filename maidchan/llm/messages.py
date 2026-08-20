# -*- coding: utf-8 -*-
"""把人设、档案、记忆与历史拼装成发送给 API 的 messages。"""

from ..config.constants import MAX_CONTEXT_TURNS, MAX_MEMORY_INJECT_TOKENS


def build_chat_messages(system_prompt, profile, history, memories=None,
                        max_context_turns=MAX_CONTEXT_TURNS):
    """构造 OpenAI 格式的 messages 列表。

    拼接顺序：档案前缀 + 相关记忆 + 人设 system prompt，
    再追加最近若干轮历史。
    """
    prefix = profile.as_prompt_prefix()
    memory_text = _format_memories(memories) if memories else ""
    sys_content = prefix + memory_text + system_prompt
    messages = [{"role": "system", "content": sys_content}]
    messages.extend(history.context_messages(max_context_turns))
    return messages


def _format_memories(memories):
    """将记忆列表格式化为 system prompt 中的文本块。

    总字符数不超过 MAX_MEMORY_INJECT_TOKENS，超出时截断后面的记忆。
    """
    if not memories:
        return ""
    header = (
        "【可能相关的记忆（仅在与当前话题直接相关时才自然融入回答，"
        "不要主动罗列或强行关联往事）】\n"
    )
    budget = MAX_MEMORY_INJECT_TOKENS - len(header)
    lines = []
    used = 0
    for m in memories:
        content = m.get("content", "")
        mem_type = m.get("type", "")
        created = m.get("created_at", "")[:10]
        if mem_type == "episode":
            line = f"- [{created}] {content}"
        else:
            line = f"- {content}"
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line) + 1  # +1 for newline
    if not lines:
        return ""
    return header + "\n".join(lines) + "\n\n"
