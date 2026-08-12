# -*- coding: utf-8 -*-
"""御主（主人）档案存储。"""

from ..config.paths import PROFILE_PATH
from .json_io import load_json, save_json


class Profile:
    """御主（主人）档案。"""

    FIELDS = [
        ("nickname", "你的昵称"),
        ("birthday", "你的生日"),
        ("call_me", "希望角色怎么称呼你"),
        ("relationship", "你们的关系设定"),
        ("extra", "其它想让角色知道的事"),
    ]

    def __init__(self):
        self.data = load_json(PROFILE_PATH, {})

    def get(self, key):
        return self.data.get(key, "")

    def update(self, new_data):
        self.data = new_data
        save_json(PROFILE_PATH, self.data)

    def as_prompt_prefix(self):
        """把档案拼成放在 system prompt 最前面的文字，空字段忽略。"""
        lines = []
        mapping = {
            "nickname": "主人的昵称",
            "birthday": "主人的生日",
            "call_me": "主人希望你这样称呼TA",
            "relationship": "你和主人的关系",
            "extra": "其它信息",
        }
        for key, label in mapping.items():
            val = str(self.data.get(key, "")).strip()
            if val:
                lines.append("%s：%s" % (label, val))
        if not lines:
            return ""
        return "【关于你的主人（务必牢记）】\n" + "\n".join(lines) + "\n\n"
