"""Programmatic configuration for the AI Game Platform.

For quick setup, use the .env file instead (see .env.example).
This module is for advanced users who want to configure the game
directly in Python code.

Usage:
    from config import build_from_dict
    from games.werewolf.engine import WerewolfEngine

    engine = WerewolfEngine(build_from_dict({
        "deepseek": {"key": "sk-xxx", "model": "deepseek-chat", "count": 2, "base_url": ""},
        "openai":   {"key": "sk-xxx", "model": "gpt-4o",         "count": 2, "base_url": ""},
        "gemini":   {"key": "xxx",    "model": "gemini-2.0-flash","count": 1, "base_url": ""},
    }))
    engine.run()
"""

import itertools
from typing import Dict, List

from core.models.factory import create_model
from core.utils import Colors
from games.werewolf.player import WerewolfPlayer

# ---- Persona pool ----

_PERSONAS = [
    "You are a logical and analytical thinker. You rely on evidence and deduction.",
    "You trust your gut instincts. You make quick judgments based on intuition.",
    "You are aggressive and quick to accuse. You like to take the lead.",
    "You are cautious and prefer to observe before speaking. You notice details others miss.",
    "You are diplomatic and try to build consensus. You mediate conflicts.",
    "You are quiet but sharply observant. When you do speak, people listen.",
    "You are charismatic and persuasive. You can talk your way out of anything.",
    "You are skeptical and question everything. You trust no one easily.",
    "You are a wildcard — unpredictable and prone to sudden shifts in opinion.",
    "You play the long game. You plant seeds of doubt and let them grow.",
]

_NAME_POOL = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank",
    "Grace", "Henry", "Iris", "Jack", "Kate", "Leo",
]


def build_from_dict(
    providers: Dict[str, Dict],
    player_names: List[str] | None = None,
) -> List[WerewolfPlayer]:
    """Build a list of WerewolfPlayers from a provider configuration dict.

    Args:
        providers: Dict mapping provider name to config dict.
            Each config dict may contain:
                key      - API key (required)
                model    - Model name (uses provider default if omitted)
                count    - How many players to create with this model (default 1)
                base_url - Override API base URL (uses provider default if omitted)
                temperature - Sampling temperature (default 0.8)
                max_tokens  - Max output tokens (default 1024)

            Example:
                {
                    "deepseek": {"key": "sk-xxx", "model": "deepseek-chat", "count": 2},
                    "openai":   {"key": "sk-xxx", "model": "gpt-4o",       "count": 3},
                    "gemini":   {"key": "xxx",    "count": 1},
                    "qwen":     {"key": "sk-xxx", "model": "qwen-max",   "count": 1,
                                 "base_url": "https://custom.endpoint.com/v1"},
                }

        player_names: Custom names for players. Cycles if shorter than total count.

    Returns:
        List of WerewolfPlayer instances ready for WerewolfEngine.
    """
    names = itertools.cycle(player_names or _NAME_POOL)
    personas = itertools.cycle(_PERSONAS)
    players = []

    for provider, cfg in providers.items():
        if "key" not in cfg:
            print(Colors.color(
                f"⚠  Skipping '{provider}': no 'key' in config", Colors.YELLOW
            ))
            continue

        count = cfg.get("count", 1)

        model_kwargs = {}
        for opt in ("temperature", "max_tokens"):
            if opt in cfg:
                model_kwargs[opt] = cfg[opt]

        model = create_model(
            provider=provider,
            api_key=cfg["key"],
            model=cfg.get("model", ""),
            base_url=cfg.get("base_url", ""),
            **model_kwargs,
        )

        for _ in range(count):
            players.append(WerewolfPlayer(
                name=next(names),
                model=model,
                persona=next(personas),
            ))

    return players


# ---- Direct construction (most flexible) ----

def build_manual(players_config: List[Dict]) -> List[WerewolfPlayer]:
    """Build players with per-player model control.

    Each entry in players_config:
        {
            "name": "Alice",
            "provider": "deepseek",
            "key": "sk-xxx",
            "model": "deepseek-chat",     # optional
            "base_url": "...",            # optional
            "persona": "You are logical", # optional
            "temperature": 0.8,           # optional
        }

    This allows every player to use a different model, API key, or endpoint.
    """
    players = []
    for i, cfg in enumerate(players_config):
        name = cfg.get("name", _NAME_POOL[i % len(_NAME_POOL)])
        persona = cfg.get("persona", _PERSONAS[i % len(_PERSONAS)])

        model = create_model(
            provider=cfg["provider"],
            api_key=cfg["key"],
            model=cfg.get("model", ""),
            base_url=cfg.get("base_url", ""),
            temperature=cfg.get("temperature", 0.8),
            max_tokens=cfg.get("max_tokens", 1024),
        )

        players.append(WerewolfPlayer(name=name, model=model, persona=persona))

    return players
