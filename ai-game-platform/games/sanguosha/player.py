"""Three Kingdoms Kill Player."""

from enum import Enum

from core.player import Player
from core.models.base import ModelInterface
from .cards import Card, CardType
from .skills import SkillID


class Identity(Enum):
    LORD = "lord"         # 主公
    LOYALIST = "loyalist"  # 忠臣
    REBEL = "rebel"        # 反贼
    SPY = "spy"            # 内奸


IDENTITY_NAMES = {
    Identity.LORD: "主公",
    Identity.LOYALIST: "忠臣",
    Identity.REBEL: "反贼",
    Identity.SPY: "内奸",
}

IDENTITY_DISTRIBUTION = {
    4: [Identity.LORD, Identity.LOYALIST, Identity.REBEL, Identity.SPY],
    5: [Identity.LORD, Identity.LOYALIST, Identity.REBEL, Identity.REBEL, Identity.SPY],
    6: [Identity.LORD, Identity.LOYALIST, Identity.REBEL, Identity.REBEL, Identity.REBEL, Identity.SPY],
    7: [Identity.LORD, Identity.LOYALIST, Identity.LOYALIST, Identity.REBEL, Identity.REBEL, Identity.REBEL, Identity.SPY],
    8: [Identity.LORD, Identity.LOYALIST, Identity.LOYALIST, Identity.REBEL, Identity.REBEL, Identity.REBEL, Identity.REBEL, Identity.SPY],
}


class SanguoshaPlayer(Player):
    def __init__(self, name: str, model: ModelInterface, persona: str = ""):
        super().__init__(name, model, persona)
        self.hp = 4
        self.max_hp = 4
        self.hand: list[Card] = []
        self.skill: SkillID | None = None
        self.sha_used = False  # whether 杀 was used this turn
        self.alive = True
        self.identity: Identity | None = None
        self.identity_revealed: bool = False  # True for lord and dead players

    @property
    def card_count(self) -> int:
        return len(self.hand)

    @property
    def is_alive(self) -> bool:
        return self.alive

    def is_enemy(self, other: "SanguoshaPlayer") -> bool:
        """Check whether `other` is an enemy of this player.
        In free_for_all mode: everyone else is an enemy.
        In identity mode: depends on faction relationships."""
        if other is self:
            return False
        if self.identity is None or other.identity is None:
            return True  # free_for_all fallback

        i_self = self.identity
        i_other = other.identity

        if i_self == Identity.LORD:
            return i_other in (Identity.REBEL, Identity.SPY)
        if i_self == Identity.LOYALIST:
            return i_other in (Identity.REBEL, Identity.SPY)
        if i_self == Identity.REBEL:
            return i_other in (Identity.LORD, Identity.LOYALIST, Identity.SPY)
        if i_self == Identity.SPY:
            return True  # spy considers everyone an enemy
        return True

    def has_card(self, card_type: CardType) -> bool:
        return any(c.card_type == card_type for c in self.hand)

    def has_any(self, *types: CardType) -> bool:
        return any(self.has_card(t) for t in types)

    def find_card(self, card_type: CardType) -> Card | None:
        for c in self.hand:
            if c.card_type == card_type:
                return c
        return None

    def remove_card(self, card: Card) -> None:
        if card in self.hand:
            self.hand.remove(card)

    def take_damage(self, amount: int = 1) -> None:
        self.hp -= amount
