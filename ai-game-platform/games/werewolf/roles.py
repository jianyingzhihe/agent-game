"""狼人杀游戏的角色与人数配置。"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class Faction(Enum):
    """角色所属阵营。"""

    VILLAGER = "villager"
    WEREWOLF = "werewolf"


@dataclass(frozen=True)
class Role:
    """角色定义。"""

    role_id: str
    name: str
    faction: Faction
    description: str

    def __repr__(self) -> str:
        return f"Role({self.name}, faction={self.faction.value})"


WEREWOLF = Role(
    "werewolf",
    "狼人",
    Faction.WEREWOLF,
    "你是狼人。每晚你和狼人队友需要共同选择一名玩家击杀。白天你要伪装成好人，"
    "通过发言和投票隐藏身份。你知道其他狼人的身份，需要与他们配合，在不暴露的前提下淘汰好人。",
)

VILLAGER = Role(
    "villager",
    "村民",
    Faction.VILLAGER,
    "你是普通村民。你没有夜间技能，但可以在白天通过发言、推理和投票找出隐藏在人群中的狼人。",
)

SEER = Role(
    "seer",
    "预言家",
    Faction.VILLAGER,
    "你是预言家。每晚你可以查验一名玩家，得知其是狼人还是好人。"
    "你需要利用这些信息带领好人推进局势，但也要注意自己可能成为狼人的刀口。",
)

WITCH = Role(
    "witch",
    "女巫",
    Faction.VILLAGER,
    "你是女巫。你拥有一瓶解药和一瓶毒药，每种药全局只能使用一次。"
    "每晚你会得知狼人击杀的目标，可以决定是否使用解药救人，也可以决定是否使用毒药带走一名玩家。",
)

HUNTER = Role(
    "hunter",
    "猎人",
    Faction.VILLAGER,
    "你是猎人。当你死亡时，无论是夜晚被杀还是白天被放逐，你都可以立即开枪带走一名玩家。"
    "这把枪只有一次，务必谨慎使用。",
)


ROLE_LIBRARY: Dict[str, Role] = {
    role.role_id: role
    for role in [WEREWOLF, VILLAGER, SEER, WITCH, HUNTER]
}


ROLE_SETS: Dict[int, List[Role]] = {
    5: [WEREWOLF, WEREWOLF, SEER, WITCH, VILLAGER],
    6: [WEREWOLF, WEREWOLF, SEER, WITCH, VILLAGER, VILLAGER],
    7: [WEREWOLF, WEREWOLF, SEER, WITCH, HUNTER, VILLAGER, VILLAGER],
    8: [WEREWOLF, WEREWOLF, SEER, WITCH, HUNTER, VILLAGER, VILLAGER, VILLAGER],
    9: [WEREWOLF, WEREWOLF, WEREWOLF, SEER, WITCH, HUNTER, VILLAGER, VILLAGER, VILLAGER],
    10: [WEREWOLF, WEREWOLF, WEREWOLF, SEER, WITCH, HUNTER, VILLAGER, VILLAGER, VILLAGER, VILLAGER],
}

SUPPORTED_PLAYER_COUNTS = tuple(sorted(ROLE_SETS))
MIN_PLAYERS = SUPPORTED_PLAYER_COUNTS[0]
MAX_PLAYERS = SUPPORTED_PLAYER_COUNTS[-1]
RECOMMENDED_STANDARD_PLAYER_COUNT = 9


def get_role_set(num_players: int) -> List[Role]:
    """按人数返回角色模板。"""
    if num_players < MIN_PLAYERS:
        raise ValueError(
            f"狼人杀至少需要 {MIN_PLAYERS} 名玩家，当前只有 {num_players} 名。"
        )

    if num_players in ROLE_SETS:
        return list(ROLE_SETS[num_players])

    base = max(count for count in ROLE_SETS if count < num_players)
    roles = list(ROLE_SETS[base])
    roles.extend([VILLAGER] * (num_players - len(roles)))
    return roles


def get_supported_player_counts() -> List[int]:
    """返回经典支持人数。"""
    return list(SUPPORTED_PLAYER_COUNTS)


def get_standard_role_set() -> List[Role]:
    """返回推荐的标准局配置。"""
    return list(ROLE_SETS[RECOMMENDED_STANDARD_PLAYER_COUNT])
