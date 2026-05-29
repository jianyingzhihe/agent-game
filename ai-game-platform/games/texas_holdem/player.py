"""Texas Hold'em Player class."""

from typing import List, Optional

from core.player import Player
from core.models.base import ModelInterface

from .cards import Card


class PokerPlayer(Player):
    """A player in Texas Hold'em."""

    def __init__(self, name: str, model: ModelInterface, chips: int = 1000, persona: str = ""):
        super().__init__(name, model, persona)
        self.chips = chips
        self.hole_cards: List[Card] = []
        self.folded = False
        self.current_bet = 0
        self.total_bet = 0

    def reset_for_hand(self):
        self.hole_cards = []
        self.folded = False
        self.current_bet = 0
        self.total_bet = 0

    def bet(self, amount: int) -> int:
        """Place a bet, returning the actual amount bet."""
        actual = min(amount, self.chips)
        self.chips -= actual
        self.current_bet += actual
        self.total_bet += actual
        return actual
