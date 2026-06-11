"""Gambler game runner — wires up models, creates engine, runs the game."""

from core.game_launcher import build_models_and_names, check_models, print_players
from core.utils import Colors

from .engine import GamblerEngine
from .player import GamblerPlayer


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Gambler — High-Stakes Betting Game "))

    entries = check_models(build_models_and_names())

    if len(entries) < 1:
        print(Colors.color("  Need at least 1 player for gambler", Colors.RED))
        return

    players = [
        GamblerPlayer(name=n, model=m, persona=p)
        for n, m, p in entries[:8]  # Cap at 8 players
    ]
    print_players(players)

    config = {}
    if max_rounds:
        config["max_rounds"] = max_rounds

    engine = GamblerEngine(players, config=config, logger=logger)
    engine.run(verbose=verbose)
