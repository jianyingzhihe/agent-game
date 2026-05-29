"""Avalon game runner."""

from core.game_launcher import build_models_and_names, check_models, print_players
from core.utils import Colors

from .engine import AvalonEngine
from .player import AvalonPlayer


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Avalon (阿瓦隆)"))
    entries = check_models(build_models_and_names())
    players = [AvalonPlayer(n, m, p) for n, m, p in entries]
    print_players(players)
    engine = AvalonEngine(players, logger=logger)
    engine.run(max_rounds=max_rounds, verbose=verbose)
