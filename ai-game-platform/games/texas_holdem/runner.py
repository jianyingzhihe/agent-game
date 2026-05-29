"""Texas Hold'em game runner."""

from core.game_launcher import build_models_and_names, check_models
from core.utils import Colors

from .engine import PokerEngine
from .player import PokerPlayer


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Texas Hold'em (德州扑克)"))
    entries = check_models(build_models_and_names())

    if len(entries) < 2:
        print(Colors.color("  Need 2+ players for poker", Colors.RED))
        return

    players = [PokerPlayer(n, m, chips=1000, persona=p) for n, m, p in entries[:6]]
    for p in players:
        print(f"  {p.name:12s} {p.chips} chips  [{p.model.model_name}]")

    engine = PokerEngine(players, logger=logger)
    engine.run(max_rounds=max_rounds, verbose=verbose)
