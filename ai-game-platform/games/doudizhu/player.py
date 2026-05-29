"""Dou Dizhu Player."""

from core.player import Player
from core.models.base import ModelInterface


class DoudizhuPlayer(Player):
    """A Dou Dizhu player with hand management."""

    def __init__(self, name: str, model: ModelInterface, persona: str = ""):
        super().__init__(name, model, persona)
        self.hand: list = []
        self.role = ""  # "landlord" or "farmer"
        self.score = 0
        self.passed = False  # passed this trick
        self.consecutive_passes = 0

    def remove_cards(self, cards: list) -> None:
        for c in cards:
            self.hand.remove(c)

    def record_pass(self) -> None:
        self.consecutive_passes += 1

    def record_play(self) -> None:
        self.consecutive_passes = 0

    @property
    def card_count(self) -> int:
        return len(self.hand)
