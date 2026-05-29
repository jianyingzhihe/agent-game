"""Dou Dizhu game runner."""

from core.game_launcher import build_models_and_names, check_models, env
from core.utils import Colors

from .engine import DoudizhuEngine
from .player import DoudizhuPlayer


DEFAULT_PLAYER_CONFIG = "deepseek:deepseek-v4-pro:1,dashscope:kimi-k2-thinking:1,dashscope:glm-5.1:1"


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Dou Dizhu (斗地主)"))
    ddz_cfg = env("DOUDIZHU_PLAYER_CONFIG", DEFAULT_PLAYER_CONFIG)
    entries = build_models_and_names(ddz_cfg)

    if len(entries) < 3:
        print(Colors.color("  Need exactly 3 players", Colors.RED))
        return

    entries = check_models(entries[:3])
    if len(entries) < 3:
        print(Colors.color("  Need 3 working players for Dou Dizhu", Colors.RED))
        return

    players = [DoudizhuPlayer(n, m, p) for n, m, p in entries[:3]]
    for p in players:
        print(f"  {p.name:12s} [{p.model.model_name}]")

    engine = DoudizhuEngine(players, logger=logger)
    engine.run(max_rounds=max_rounds, verbose=verbose)
