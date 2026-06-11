#!/usr/bin/env python3
"""Thin entry point for launching a specific game runner."""

import importlib
import os
import sys

# Force UTF-8 output on Windows to avoid GBK encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()
if not os.getenv("DEEPSEEK_KEY") and not os.getenv("OPENAI_KEY"):
    project_root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(project_root, ".env"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.game_launcher import env, env_bool
from core.logger import GameLogger


GAME_RUNNERS = {
    "werewolf": "games.werewolf.runner",
    "avalon": "games.avalon.runner",
    "codenames": "games.codenames.runner",
    "texas_holdem": "games.texas_holdem.runner",
    "poker": "games.texas_holdem.runner",
    "texas": "games.texas_holdem.runner",
    "doudizhu": "games.doudizhu.runner",
    "dou": "games.doudizhu.runner",
    "sanguosha": "games.sanguosha.runner",
    "sgs": "games.sanguosha.runner",
    "gambler": "games.gambler.runner",
    "gamble": "games.gambler.runner",
}


def resolve_game_type() -> str:
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower().strip()
        if arg in ("models", "--models", "-m"):
            return "models"
        return arg
    return env("GAME_TYPE", "werewolf").lower().strip()


def load_runner(game_type: str):
    module_name = GAME_RUNNERS.get(game_type)
    if not module_name:
        print(f"Unknown GAME_TYPE: {game_type}")
        print("Available: werewolf, avalon, codenames, texas_holdem, doudizhu, gambler")
        sys.exit(1)
    module = importlib.import_module(module_name)
    return module.run


def main():
    game_type = resolve_game_type()

    if game_type == "models":
        from core.game_launcher import list_available_models
        list_available_models()
        return

    log_dir = env("LOG_DIR", "logs")
    logger = GameLogger(game_type, base_dir=log_dir)
    max_rounds = int(env("MAX_ROUNDS", "50"))
    verbose = env_bool("VERBOSE", True)
    runner = load_runner(game_type)
    runner(logger, max_rounds, verbose)


if __name__ == "__main__":
    main()
