"""Codenames-specific Player class."""

from core.player import Player
from core.models.base import ModelInterface


class CodenamesPlayer(Player):
    """A player in Codenames — either spymaster or guesser for their team."""

    def __init__(self, name: str, model: ModelInterface, team: str, role: str, persona: str = ""):
        super().__init__(name, model, persona)
        self.team = team     # "red" or "blue"
        self.role = role     # "spymaster" or "guesser"

    @property
    def is_spymaster(self) -> bool:
        return self.role == "spymaster"

    @property
    def is_guesser(self) -> bool:
        return self.role == "guesser"
