"""Werewolf game runner."""

from core.game_launcher import build_models_and_names, check_models, env, print_players
from core.utils import Colors

from .engine import WerewolfEngine
from .player import WerewolfPlayer


DEFAULT_PLAYER_CONFIG = "deepseek:2,openai:2,qwen:2"


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Werewolf (鐙间汉鏉€)"))
    ww_cfg = env("WEREWOLF_PLAYER_CONFIG", env("PLAYER_CONFIG", DEFAULT_PLAYER_CONFIG))
    entries = check_models(build_models_and_names(ww_cfg))
    players = [WerewolfPlayer(n, m, p) for n, m, p in entries]
    print_players(players)
    engine = WerewolfEngine(players, logger=logger)
    engine.run(max_rounds=max_rounds, verbose=verbose)
