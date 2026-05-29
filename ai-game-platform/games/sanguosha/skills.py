"""Skills for Three Kingdoms Kill."""

import random
from enum import Enum
from typing import List


class SkillID(Enum):
    SWAP = "swap"            # 杀当闪闪当杀
    UNLIMITED_SHA = "unlim"  # 无限出杀
    BLOOD_DRAW = "blood"     # 主动扣1血摸2张
    WOUND_DRAW = "wound"     # 受伤摸2张
    WOUND_STEAL = "steal"    # 受伤拿来源1张牌
    EMPTY_DRAW = "empty"     # 回合结束无手牌摸1张
    EMPTY_IMMUNE = "immune"  # 无手牌不能被指定为杀的目标


SKILL_INFO = {
    SkillID.SWAP: {
        "name": "武圣",
        "desc": "你可以将【杀】当【闪】使用，或将【闪】当【杀】使用。",
    },
    SkillID.UNLIMITED_SHA: {
        "name": "咆哮",
        "desc": "你使用【杀】没有次数限制。",
    },
    SkillID.BLOOD_DRAW: {
        "name": "苦肉",
        "desc": "出牌阶段，你可以主动扣1点体力，摸2张牌。",
    },
    SkillID.WOUND_DRAW: {
        "name": "刚烈",
        "desc": "每当你受到1点伤害后，你可以摸2张牌。",
    },
    SkillID.WOUND_STEAL: {
        "name": "反馈",
        "desc": "每当你受到1点伤害后，你可以获得伤害来源的1张手牌。",
    },
    SkillID.EMPTY_DRAW: {
        "name": "空城",
        "desc": "回合结束阶段，若你没有手牌，你可以摸1张牌。",
    },
    SkillID.EMPTY_IMMUNE: {
        "name": "空城·守",
        "desc": "若你没有手牌，你不能成为【杀】的目标。",
    },
}


def random_skill() -> SkillID:
    return random.choice(list(SkillID))
