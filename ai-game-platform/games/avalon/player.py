"""Avalon-specific Player class."""

from typing import Optional

from core.player import Player
from core.models.base import ModelInterface

from .roles import Role


class AvalonPlayer(Player):
    """A player in Avalon with role awareness."""

    def __init__(self, name: str, model: ModelInterface, persona: str = ""):
        super().__init__(name, model, persona)
        self.role: Optional[Role] = None
        self.known_evil: list[str] = []       # Evil players this player knows
        self.merlin_candidates: list[str] = [] # For Percival: [Merlin, Morgana]

    def assign_role(self, role: Role) -> None:
        self.role = role

    @property
    def faction(self) -> str:
        return self.role.faction.value if self.role else "unknown"

    @property
    def is_good(self) -> bool:
        return self.role is not None and self.role.faction.value == "good"

    @property
    def is_evil(self) -> bool:
        return self.role is not None and self.role.faction.value == "evil"

    def get_system_prompt(self, all_players: list) -> str:
        from .prompts import build_system_prompt

        evil = self.known_evil if self.role and self.role.role_id == "merlin" else None
        if self.is_evil:
            evil = self.known_evil  # fellow evil
        return build_system_prompt(
            player_name=self.name,
            role=self.role,
            all_players=all_players,
            known_evil=evil,
            merlin_candidates=self.merlin_candidates or None,
        )
