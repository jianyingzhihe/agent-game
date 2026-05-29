"""Role definitions for the Werewolf game."""

from enum import Enum
from typing import Dict, List


class Faction(Enum):
    """Which side a role belongs to."""

    VILLAGER = "villager"  # Good team
    WEREWOLF = "werewolf"  # Evil team


class Role:
    """A role definition with name, faction, and description."""

    def __init__(self, role_id: str, name: str, faction: Faction, description: str):
        self.role_id = role_id
        self.name = name
        self.faction = faction
        self.description = description

    def __repr__(self) -> str:
        return f"Role({self.name}, faction={self.faction.value})"


# ---- Standard Roles ----

WEREWOLF = Role(
    "werewolf",
    "Werewolf (狼人)",
    Faction.WEREWOLF,
    "You are a Werewolf. Each night you and your fellow werewolves choose one player "
    "to kill. During the day you must pretend to be a villager. You know who the other "
    "werewolves are. Work together to eliminate the villagers without being discovered.",
)

VILLAGER = Role(
    "villager",
    "Villager (村民)",
    Faction.VILLAGER,
    "You are an ordinary Villager. You have no special night abilities but you can "
    "participate in discussion and vote during the day. Use logic and observation "
    "to identify the werewolves hiding among you.",
)

SEER = Role(
    "seer",
    "Seer (预言家)",
    Faction.VILLAGER,
    "You are the Seer. Each night you can check one player's identity to learn "
    "whether they are a Werewolf or a Villager. Use this information to guide "
    "the village, but be careful — revealing yourself makes you a target.",
)

WITCH = Role(
    "witch",
    "Witch (女巫)",
    Faction.VILLAGER,
    "You are the Witch. You possess two potions: one Antidote (解药) to save a "
    "player from death, and one Poison (毒药) to kill a player. You may use each "
    "potion only ONCE per game. Each night you will be told who the werewolves "
    "targeted. You may save that player with your antidote, and/or poison another.",
)

HUNTER = Role(
    "hunter",
    "Hunter (猎人)",
    Faction.VILLAGER,
    "You are the Hunter. When you die (whether killed by werewolves or voted out), "
    "you may immediately shoot one player to take them down with you. Use this "
    "ability wisely — you only get one shot.",
)

# ---- Role Sets for Different Player Counts ----
# Key: number of players, Value: list of roles

ROLE_SETS: Dict[int, List[Role]] = {
    5: [WEREWOLF, WEREWOLF, SEER, WITCH, VILLAGER],
    6: [WEREWOLF, WEREWOLF, SEER, WITCH, VILLAGER, VILLAGER],
    7: [WEREWOLF, WEREWOLF, SEER, WITCH, HUNTER, VILLAGER, VILLAGER],
    8: [WEREWOLF, WEREWOLF, SEER, WITCH, HUNTER, VILLAGER, VILLAGER, VILLAGER],
    9: [
        WEREWOLF,
        WEREWOLF,
        WEREWOLF,
        SEER,
        WITCH,
        HUNTER,
        VILLAGER,
        VILLAGER,
        VILLAGER,
    ],
    10: [
        WEREWOLF,
        WEREWOLF,
        WEREWOLF,
        SEER,
        WITCH,
        HUNTER,
        VILLAGER,
        VILLAGER,
        VILLAGER,
        VILLAGER,
    ],
}


def get_role_set(num_players: int) -> List[Role]:
    """Get the recommended role set for a given number of players.

    Falls back to the closest predefined set, then pads with villagers.
    """
    if num_players in ROLE_SETS:
        return list(ROLE_SETS[num_players])

    # Find the largest predefined set smaller than num_players
    base = max(k for k in ROLE_SETS if k < num_players)
    roles = list(ROLE_SETS[base])
    extra = num_players - len(roles)
    roles.extend([VILLAGER] * extra)
    return roles
