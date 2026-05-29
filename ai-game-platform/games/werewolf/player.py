"""Werewolf-specific Player class."""

from typing import Optional

from core.player import Player
from core.models.base import ModelInterface

from .roles import Role


class WerewolfPlayer(Player):
    """A player in the Werewolf game with role awareness.

    Extends the base Player with:
    - Role assignment and faction knowledge
    - Knowledge of fellow werewolves (for werewolf role)
    - Last-will / death message
    """

    def __init__(
        self,
        name: str,
        model: ModelInterface,
        persona: str = "",
    ):
        super().__init__(name, model, persona)
        self.role: Optional[Role] = None
        self.fellow_wolves: list[str] = []
        self.death_message: str = ""

    def assign_role(self, role: Role) -> None:
        """Assign a role to this player."""
        self.role = role

    @property
    def faction(self) -> str:
        """Get this player's faction."""
        return self.role.faction.value if self.role else "unknown"

    @property
    def is_werewolf(self) -> bool:
        return self.role is not None and self.role.role_id == "werewolf"

    @property
    def is_villager_team(self) -> bool:
        return self.role is not None and self.role.faction.value == "villager"

    def get_system_prompt(self, all_players: list) -> str:
        """Build the system prompt for this player."""
        from .prompts import build_system_prompt

        wolves = self.fellow_wolves if self.is_werewolf else None
        return build_system_prompt(
            player_name=self.name,
            role=self.role,
            all_players=all_players,
            fellow_wolves=wolves,
        )

    def __repr__(self) -> str:
        role_name = self.role.name if self.role else "unassigned"
        status = "alive" if self.alive else "dead"
        return f"WerewolfPlayer({self.name}, {role_name}, {self.model.model_name}, {status})"
