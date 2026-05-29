"""Codenames game runner."""

from core.game_launcher import build_models_and_names, check_models
from core.utils import Colors

from .engine import CodenamesEngine
from .player import CodenamesPlayer


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Codenames"))
    entries = check_models(build_models_and_names())

    if len(entries) < 4:
        print(Colors.color("  Need 4+ players for Codenames (2 teams x spymaster+guesser)", Colors.RED))
        return

    players = []
    for i, (name, model, persona) in enumerate(entries[:4]):
        if i < 2:
            team, role = "red", "spymaster" if i == 0 else "guesser"
        else:
            team, role = "blue", "spymaster" if i == 2 else "guesser"
        players.append(CodenamesPlayer(name, model, team, role, persona))

    for p in players:
        print(f"  {p.name:12s} [{p.team.upper()} {p.role.upper()}] {p.model.model_name}")

    engine = CodenamesEngine(players, logger=logger)
    engine.run(max_rounds=max_rounds, verbose=verbose)
