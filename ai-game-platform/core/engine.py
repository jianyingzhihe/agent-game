"""Base GameEngine - abstract foundation for all turn-based games.

To add a new game, subclass GameEngine and implement:
- setup(): Initialize game state (roles, board, etc.)
- step(): Execute one round/phase
- check_win(): Return winner faction or None
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .player import Player
from .utils import Colors


class GameEngine(ABC):
    """Abstract base class for turn-based game engines.

    Provides:
    - Player management (alive/dead tracking)
    - Round counting and logging
    - Win-condition checking loop
    - Pretty-printing helpers
    """

    def __init__(self, players: List[Player], config: Optional[Dict] = None):
        """Initialize the game engine.

        Args:
            players: List of Player instances (order may be shuffled)
            config: Game-specific configuration dict
        """
        if len(players) < 3:
            raise ValueError("Need at least 3 players")

        self.players = players
        self.config = config or {}
        self.round = 0
        self.log: List[Dict[str, Any]] = []
        self.finished = False
        self.winner: Optional[str] = None

    # ---- Subclass interface ----

    @abstractmethod
    def setup(self) -> None:
        """Initialize the game: assign roles, shuffle, deal cards, etc.

        Called once before the first round.
        """
        ...

    @abstractmethod
    def step(self) -> Dict[str, Any]:
        """Execute one round/phase of the game.

        Returns:
            A dict describing what happened this round, for logging/display.
        """
        ...

    @abstractmethod
    def check_win(self) -> Optional[str]:
        """Check if the game is over.

        Returns:
            The name of the winning faction, or None if the game continues.
        """
        ...

    # ---- Public API ----

    def run(
        self,
        max_rounds: int = 100,
        verbose: bool = True,
    ) -> Optional[str]:
        """Run the game from start to finish.

        Args:
            max_rounds: Safety limit to prevent infinite loops
            verbose: Print game events to stdout

        Returns:
            Winner faction name, or None if max_rounds reached
        """
        self.setup()

        if verbose:
            self._print_header("GAME START")
            self._print_setup()

        while not self.finished and self.round < max_rounds:
            self.round += 1

            if verbose:
                print(f"\n{'─' * 55}")
                print(Colors.bold(f" Round {self.round} "))
                print(f"{'─' * 55}")

            round_result = self.step()
            self.log.append(round_result)

            winner = self.check_win()
            if winner:
                self.finished = True
                self.winner = winner
                if verbose:
                    self._print_result()

        if self.round >= max_rounds and not self.finished:
            if verbose:
                print(Colors.color(f"\nGame stopped: max rounds ({max_rounds}) reached.", Colors.YELLOW))

        return self.winner

    # ---- Properties ----

    @property
    def alive_players(self) -> List[Player]:
        """Currently alive players."""
        return [p for p in self.players if p.alive]

    @property
    def dead_players(self) -> List[Player]:
        """Currently dead players."""
        return [p for p in self.players if not p.alive]

    @property
    def alive_count(self) -> int:
        return len(self.alive_players)

    # ---- Display helpers (override for better output) ----

    def _print_header(self, text: str) -> None:
        print(f"\n{Colors.bold('=' * 55)}")
        print(Colors.bold(f"  {text}"))
        print(Colors.bold('=' * 55))

    @abstractmethod
    def _print_setup(self) -> None:
        """Print the initial game setup."""
        ...

    @abstractmethod
    def _print_result(self) -> None:
        """Print the final result."""
        ...
