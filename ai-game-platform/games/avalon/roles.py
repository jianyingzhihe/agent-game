"""Role definitions for Avalon."""

from enum import Enum
from typing import Dict, List


class Faction(Enum):
    GOOD = "good"
    EVIL = "evil"


class Role:
    def __init__(self, role_id: str, name: str, faction: Faction, description: str):
        self.role_id = role_id
        self.name = name
        self.faction = faction
        self.description = description


# ---- Roles ----

MERLIN = Role(
    "merlin", "Merlin (梅林)",
    Faction.GOOD,
    "You are Merlin. You know who the evil players are (except Mordred if present). "
    "Guide the good team subtly — if you're too obvious, the Assassin will kill you "
    "after a Good victory and steal the win.",
)

PERCIVAL = Role(
    "percival", "Percival (派西维尔)",
    Faction.GOOD,
    "You are Percival. You know who Merlin is (but not which of the two apparent "
    "Merlins is real if Morgana is in play). Use this knowledge to support the "
    "real Merlin without exposing them.",
)

LOYAL_SERVANT = Role(
    "loyal", "Loyal Servant (忠诚仆人)",
    Faction.GOOD,
    "You are a Loyal Servant of Arthur. You have no special knowledge — use logic "
    "and observation to identify evil players and ensure quests succeed.",
)

ASSASSIN = Role(
    "assassin", "Assassin (刺客)",
    Faction.EVIL,
    "You are the Assassin. You know your fellow evil players. If the Good team wins "
    "3 quests, you get ONE chance to assassinate Merlin. If you guess correctly, "
    "Evil steals the victory!",
)

MORGANA = Role(
    "morgana", "Morgana (莫甘娜)",
    Faction.EVIL,
    "You are Morgana. You appear as Merlin to Percival — Percival will see two "
    "possible Merlins (you and the real one). Confuse Percival and sabotage quests.",
)

MINION = Role(
    "minion", "Minion of Mordred (爪牙)",
    Faction.EVIL,
    "You are a Minion of Mordred. You know your fellow evil players. Sabotage "
    "quests by voting Fail, but be smart — too many Fails exposes you.",
)

# ---- Role Sets ----

ROLE_SETS: Dict[int, List[Role]] = {
    5: [MERLIN, PERCIVAL, LOYAL_SERVANT, ASSASSIN, MORGANA],
    6: [MERLIN, PERCIVAL, LOYAL_SERVANT, LOYAL_SERVANT, ASSASSIN, MORGANA],
    7: [MERLIN, PERCIVAL, LOYAL_SERVANT, LOYAL_SERVANT, ASSASSIN, MORGANA, MINION],
    8: [MERLIN, PERCIVAL, LOYAL_SERVANT, LOYAL_SERVANT, LOYAL_SERVANT, ASSASSIN, MORGANA, MINION],
}


# Quest team sizes per round, by total players
QUEST_TEAM_SIZES: Dict[int, List[int]] = {
    5: [2, 3, 2, 3, 3],
    6: [2, 3, 4, 3, 4],
    7: [2, 3, 3, 4, 4],
    8: [3, 4, 4, 5, 5],
}


def get_role_set(num_players: int) -> List[Role]:
    if num_players in ROLE_SETS:
        return list(ROLE_SETS[num_players])
    base = max(k for k in ROLE_SETS if k < num_players)
    roles = list(ROLE_SETS[base])
    extra = num_players - len(roles)
    roles.extend([LOYAL_SERVANT] * extra)
    return roles


def get_quest_sizes(num_players: int) -> List[int]:
    if num_players in QUEST_TEAM_SIZES:
        return list(QUEST_TEAM_SIZES[num_players])
    return [3, 4, 4, 5, 5]  # Default for 8+
