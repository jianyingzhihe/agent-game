"""Base Player agent - wraps an LLM model with game context.

Each player has:
- A name (identity in the game)
- A model (LLM providing intelligence)
- A persona (optional personality flavor)
- Memory (personal log of game events)
- Alive/dead state
"""

from typing import Dict, List, Optional, Tuple

from .models.base import ModelInterface


class Player:
    """A player in the game, powered by an LLM model.

    This is a lightweight wrapper. Game-specific logic should go in
    game-specific Player subclasses (e.g., WerewolfPlayer).
    """

    def __init__(
        self,
        name: str,
        model: ModelInterface,
        persona: str = "",
    ):
        """Initialize a player.

        Args:
            name: Display name in the game (e.g., 'Alice', 'Bot-1')
            model: The LLM model powering this player's decisions
            persona: Optional personality hint injected into prompts
        """
        self.name = name
        self.model = model
        self.persona = persona
        self.alive = True
        self.memory: List[str] = []  # Personal event log

    def remember(self, event: str) -> None:
        """Record an event in this player's memory."""
        self.memory.append(event)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """Send prompts to the model, returning (thinking, content)."""
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        return self.model.chat(messages, **kwargs)

    def kill(self) -> None:
        """Mark this player as dead."""
        self.alive = False

    def revive(self) -> None:
        """Mark this player as alive (e.g., saved by witch)."""
        self.alive = True

    def __repr__(self) -> str:
        status = "alive" if self.alive else "dead"
        return f"Player({self.name}, model={self.model.model_name}, {status})"

    def __str__(self) -> str:
        status = "✓" if self.alive else "✗"
        return f"[{status}] {self.name} ({self.model.model_name})"
