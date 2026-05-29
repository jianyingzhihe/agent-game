"""Werewolf game runner."""

from core.game_launcher import build_models_and_names, check_models, print_players
from core.utils import Colors

from .engine import WerewolfEngine
from .player import WerewolfPlayer


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Werewolf (狼人杀)"))
    entries = check_models(build_models_and_names())
    players = [WerewolfPlayer(n, m, p) for n, m, p in entries]
    print_players(players)
    engine = WerewolfEngine(players, logger=logger)
    engine.run(max_rounds=max_rounds, verbose=verbose)
